from typing import Dict, List, Optional, Tuple
from langchain_openai import OpenAIEmbeddings
import numpy as np
from datetime import datetime
from schemas.email_models import SenderProfile
from config import settings


class EmbeddingService:
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.EMBEDDING_MODEL
        self.embedding_model = OpenAIEmbeddings(
            model=self.model,
            api_key=settings.OPENAI_API_KEY
        )
    
    def embed_text(self, text: str) -> List[float]:
        if not text or len(text.strip()) == 0:
            return [0.0] * settings.EMBEDDING_DIMENSION
        try:
            return self.embedding_model.embed_query(text)
        except Exception as e:
            raise RuntimeError(f"Embedding failed: {str(e)}")
    
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(text) for text in texts]
    
    @staticmethod
    def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2:
            return 0.0
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(vec1, vec2) / (norm1 * norm2))
    
    @staticmethod
    def average_vectors(vectors: List[List[float]]) -> List[float]:
        if not vectors:
            return [0.0] * settings.EMBEDDING_DIMENSION
        return list(np.mean(np.array(vectors), axis=0))


class SenderProfileService:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.profiles: Dict[str, SenderProfile] = {}
        self.sender_profiles = {}
    
    def get_or_create_profile(self, sender_email: str) -> SenderProfile:
        if sender_email not in self.profiles:
            self.profiles[sender_email] = SenderProfile(sender_email=sender_email)
        return self.profiles[sender_email]
    
    def update_profile(self, sender_email: str, email_body: str, tone: str, classifications: List[str], risk_score: float) -> None:
        profile = self.get_or_create_profile(sender_email)
        profile.email_count += 1
        new_embedding = self.embedding_service.embed_text(email_body)
        if profile.average_tone_embedding is None:
            profile.average_tone_embedding = new_embedding
        else:
            profile.average_tone_embedding = self.embedding_service.average_vectors([profile.average_tone_embedding, new_embedding])
        profile.tone_history.append(tone)
        if len(profile.tone_history) > 100:
            profile.tone_history = profile.tone_history[-100:]
        profile.classification_history.extend(classifications)
        if len(profile.classification_history) > 100:
            profile.classification_history = profile.classification_history[-100:]
        profile.risk_score_history.append(risk_score)
        if len(profile.risk_score_history) > 100:
            profile.risk_score_history = profile.risk_score_history[-100:]
        profile.last_updated = datetime.now()
    
    def calculate_tone_deviation(self, sender_email: str, email_body: str) -> float:
        profile = self.get_or_create_profile(sender_email)
        if profile.average_tone_embedding is None:
            return 0.0
        current_embedding = self.embedding_service.embed_text(email_body)
        similarity = self.embedding_service.cosine_similarity(current_embedding, profile.average_tone_embedding)
        deviation = max(0.0, 1.0 - similarity)
        return min(1.0, deviation)
    
    def update_sender_profile(self, sender: str, text: str) -> None:
        emb = self.embedding_service.embed_text(text)
        if sender not in self.sender_profiles:
            self.sender_profiles[sender] = emb
        else:
            self.sender_profiles[sender] = list(np.mean([self.sender_profiles[sender], emb], axis=0))
    
    def tone_deviation(self, sender: str, text: str) -> float:
        if sender not in self.sender_profiles:
            return 1.0
        emb = self.embedding_service.embed_text(text)
        base = self.sender_profiles[sender]
        similarity = np.dot(emb, base) / (np.linalg.norm(emb) * np.linalg.norm(base))
        return 1 - similarity
    
    def export_profiles(self) -> List[SenderProfile]:
        return list(self.profiles.values())
    
    def load_profiles(self, profiles: List[SenderProfile]) -> None:
        for profile in profiles:
            self.profiles[profile.sender_email] = profile


_sender_profile_service: Optional[SenderProfileService] = None


def get_sender_profile_service() -> SenderProfileService:
    global _sender_profile_service
    if _sender_profile_service is None:
        _sender_profile_service = SenderProfileService()
    return _sender_profile_service
