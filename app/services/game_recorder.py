"""
Game recording service
"""

import logging
import json
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.models.game import Game, Speech, Vote
from app.models.user import User
from app.core.redis_client import redis_manager
from app.core.database import db_manager
from app.services.audit_logger import audit_logger, AuditEventType, data_integrity_checker

logger = logging.getLogger(__name__)


class GameRecorder:
    def __init__(self, db: Session):
        self.db = db
        self.record_key_prefix = "game:record:"
        self.record_ttl = 7776000

    def _calculate_record_checksum(self, record: Dict[str, Any]) -> str:
        sorted_data = json.dumps(record, sort_keys=True, default=str)
        return hashlib.sha256(sorted_data.encode()).hexdigest()

    async def record_game_start(self, game_id: str, game_data: Dict[str, Any]) -> bool:
        try:
            start_record = {"event": "game_start", "game_id": game_id, "timestamp": datetime.utcnow().isoformat(), "room_id": game_data.get("room_id"), "word_pair_id": game_data.get("word_pair_id"), "players": game_data.get("players", []), "settings": game_data.get("settings", {})}
            redis_client = await redis_manager.get_client()
            record_key = f"{self.record_key_prefix}{game_id}:start"
            await redis_client.setex(record_key, self.record_ttl, json.dumps(start_record, default=str))
            await audit_logger.log_event(event_type=AuditEventType.GAME_START, details={"game_id": game_id})
            return True
        except Exception as e:
            logger.error(f"Failed to record game start for {game_id}: {e}")
            return False

    async def record_speech(self, game_id: str, player_id: str, speech_data: Dict[str, Any]) -> bool:
        try:
            speech_record = {"event": "player_speech", "game_id": game_id, "player_id": player_id, "timestamp": datetime.utcnow().isoformat(), "content": speech_data.get("content"), "round_number": speech_data.get("round_number"), "speech_order": speech_data.get("speech_order")}
            redis_client = await redis_manager.get_client()
            record_key = f"{self.record_key_prefix}{game_id}:speeches"
            await redis_client.rpush(record_key, json.dumps(speech_record, default=str))
            await redis_client.expire(record_key, self.record_ttl)
            await audit_logger.log_event(event_type=AuditEventType.PLAYER_SPEECH, user_id=player_id, details={"game_id": game_id})
            return True
        except Exception as e:
            logger.error(f"Failed to record speech: {e}")
            return False

    async def record_vote(self, game_id: str, voter_id: str, vote_data: Dict[str, Any]) -> bool:
        try:
            vote_record = {"event": "player_vote", "game_id": game_id, "voter_id": voter_id, "timestamp": datetime.utcnow().isoformat(), "target_id": vote_data.get("target_id"), "round_number": vote_data.get("round_number")}
            redis_client = await redis_manager.get_client()
            record_key = f"{self.record_key_prefix}{game_id}:votes"
            await redis_client.rpush(record_key, json.dumps(vote_record, default=str))
            await redis_client.expire(record_key, self.record_ttl)
            await audit_logger.log_event(event_type=AuditEventType.PLAYER_VOTE, user_id=voter_id, details={"game_id": game_id})
            return True
        except Exception as e:
            logger.error(f"Failed to record vote: {e}")
            return False

    async def record_elimination(self, game_id: str, eliminated_player_id: str, elimination_data: Dict[str, Any]) -> bool:
        try:
            elimination_record = {"event": "player_eliminate", "game_id": game_id, "eliminated_player_id": eliminated_player_id, "timestamp": datetime.utcnow().isoformat(), "round_number": elimination_data.get("round_number"), "vote_count": elimination_data.get("vote_count"), "revealed_role": elimination_data.get("revealed_role")}
            redis_client = await redis_manager.get_client()
            record_key = f"{self.record_key_prefix}{game_id}:eliminations"
            await redis_client.rpush(record_key, json.dumps(elimination_record, default=str))
            await redis_client.expire(record_key, self.record_ttl)
            await audit_logger.log_event(event_type=AuditEventType.PLAYER_ELIMINATE, user_id=eliminated_player_id, details={"game_id": game_id})
            return True
        except Exception as e:
            logger.error(f"Failed to record elimination: {e}")
            return False

    async def record_game_finish(self, game_id: str, finish_data: Dict[str, Any]) -> bool:
        try:
            finish_record = {"event": "game_finish", "game_id": game_id, "timestamp": datetime.utcnow().isoformat(), "winner_role": finish_data.get("winner_role"), "winner_players": finish_data.get("winner_players", []), "total_rounds": finish_data.get("total_rounds"), "duration_minutes": finish_data.get("duration_minutes"), "final_players": finish_data.get("final_players", [])}
            redis_client = await redis_manager.get_client()
            record_key = f"{self.record_key_prefix}{game_id}:finish"
            await redis_client.setex(record_key, self.record_ttl, json.dumps(finish_record, default=str))
            await audit_logger.log_event(event_type=AuditEventType.GAME_FINISH, details={"game_id": game_id})
            await self._generate_game_summary(game_id)
            return True
        except Exception as e:
            logger.error(f"Failed to record game finish: {e}")
            return False

    async def _generate_game_summary(self, game_id: str) -> bool:
        try:
            redis_client = await redis_manager.get_client()
            start_data = await redis_client.get(f"{self.record_key_prefix}{game_id}:start")
            finish_data = await redis_client.get(f"{self.record_key_prefix}{game_id}:finish")
            speeches = await redis_client.lrange(f"{self.record_key_prefix}{game_id}:speeches", 0, -1)
            votes = await redis_client.lrange(f"{self.record_key_prefix}{game_id}:votes", 0, -1)
            eliminations = await redis_client.lrange(f"{self.record_key_prefix}{game_id}:eliminations", 0, -1)
            summary = {"game_id": game_id, "start": json.loads(start_data) if start_data else None, "finish": json.loads(finish_data) if finish_data else None, "speeches": [json.loads(s) for s in speeches] if speeches else [], "votes": [json.loads(v) for v in votes] if votes else [], "eliminations": [json.loads(e) for e in eliminations] if eliminations else [], "summary_generated_at": datetime.utcnow().isoformat()}
            checksum = self._calculate_record_checksum(summary)
            summary["checksum"] = checksum
            summary_key = f"{self.record_key_prefix}{game_id}:summary"
            await data_integrity_checker.store_with_checksum(summary_key, summary, self.record_ttl)
            return True
        except Exception as e:
            logger.error(f"Failed to generate game summary: {e}")
            return False

    async def get_game_record(self, game_id: str) -> Optional[Dict[str, Any]]:
        try:
            redis_client = await redis_manager.get_client()
            summary_key = f"{self.record_key_prefix}{game_id}:summary"
            integrity_result = await data_integrity_checker.verify_data_integrity(summary_key)
            if integrity_result.get("is_valid"):
                summary_data = await redis_client.get(summary_key)
                if summary_data:
                    return json.loads(summary_data)
            return None
        except Exception as e:
            logger.error(f"Failed to get game record: {e}")
            return None

    async def verify_game_record_integrity(self, game_id: str) -> Dict[str, Any]:
        try:
            record = await self.get_game_record(game_id)
            if not record:
                return {"game_id": game_id, "is_complete": False, "errors": ["游戏记录不存在"]}
            errors = []
            warnings = []
            if not record.get("start"):
                errors.append("缺少游戏开始记录")
            if not record.get("finish"):
                warnings.append("游戏尚未结束")
            speeches = record.get("speeches", [])
            votes = record.get("votes", [])
            return {"game_id": game_id, "is_complete": len(errors) == 0, "errors": errors, "warnings": warnings, "record_count": {"speeches": len(speeches), "votes": len(votes), "eliminations": len(record.get("eliminations", []))}}
        except Exception as e:
            return {"game_id": game_id, "is_complete": False, "errors": [str(e)]}


_game_recorder_instance = None


def get_game_recorder(db: Session) -> GameRecorder:
    global _game_recorder_instance
    if _game_recorder_instance is None:
        _game_recorder_instance = GameRecorder(db)
    return _game_recorder_instance


async def record_game_event(db: Session, event_type: str, game_id: str, data: Dict[str, Any]) -> bool:
    recorder = get_game_recorder(db)
    if event_type == "start":
        return await recorder.record_game_start(game_id, data)
    elif event_type == "speech":
        return await recorder.record_speech(game_id, data.get("player_id"), data)
    elif event_type == "vote":
        return await recorder.record_vote(game_id, data.get("voter_id"), data)
    elif event_type == "elimination":
        return await recorder.record_elimination(game_id, data.get("eliminated_player_id"), data)
    elif event_type == "finish":
        return await recorder.record_game_finish(game_id, data)
    return False
