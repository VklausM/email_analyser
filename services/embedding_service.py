import numpy as np
import chromadb
from chromadb.utils import embedding_functions
from langchain_openai import OpenAIEmbeddings
from datetime import datetime
from typing import Dict, List, Optional
from schemas.email_models import SenderProfile
from config import settings

class EmbeddingService:
    def __init__(self):
        self.model = OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.OPENAI_API_KEY
        )
    
    def embed_text(self, text: str) -> List[float]:
        if not text.strip():
            return [0.0] * settings.EMBEDDING_DIMENSION
        return self.model.embed_query(text)

class SenderProfileService:
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self.collection = self.client.get_or_create_collection(
            name="sender_tones",
            metadata={"hnsw:space": "cosine"}
        )
        self.profiles: Dict[str, SenderProfile] = {}

    def get_or_create_profile(self, email: str) -> SenderProfile:
        if email not in self.profiles:
            self.profiles[email] = SenderProfile(sender_email=email)
        return self.profiles[email]

    def calculate_tone_deviation(self, email: str, text: str) -> float:
        results = self.collection.get(ids=[email], include=['embeddings'])
        if results['embeddings'] is None or len(results['embeddings']) == 0:
            return 0.0
            
        current_emb = self.embedding_service.embed_text(text)
        stored_emb = results['embeddings'][0]
        
        dot_product = np.dot(current_emb, stored_emb)
        norm_a = np.linalg.norm(current_emb)
        norm_b = np.linalg.norm(stored_emb)
        
        similarity = dot_product / (norm_a * norm_b) if norm_a > 0 and norm_b > 0 else 0
        return float(max(0.0, 1.0 - similarity))

    def update_profile(self, email: str, text: str, tone: str, classifications: List[str], risk_score: float):
        profile = self.get_or_create_profile(email)
        new_emb = self.embedding_service.embed_text(text)
        
        results = self.collection.get(ids=[email], include=['embeddings'])
        if results['embeddings'] is not None and len(results['embeddings']) > 0:
            existing_emb = results['embeddings'][0]
            updated_emb = list(np.mean([existing_emb, new_emb], axis=0))
            self.collection.update(ids=[email], embeddings=[updated_emb])
        else:
            self.collection.add(ids=[email], embeddings=[new_emb])
            
        profile.email_count += 1
        profile.tone_history.append(tone)
        profile.classification_history.extend(classifications)
        profile.risk_score_history.append(risk_score)
        profile.last_updated = datetime.now()

_service = None

def get_sender_profile_service():
    global _service
    if _service is None:
        _service = SenderProfileService()
    return _service
