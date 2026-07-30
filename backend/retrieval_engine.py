"""
Retrieval Engine: Narrows down destination field candidates before LLM processing
"""

from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import re
from difflib import SequenceMatcher
from sqlalchemy.orm import Session
from models import SourceField, DestinationField, FieldMetadata


@dataclass
class RetrievalCandidate:
    """Represents a candidate destination field with scores"""
    destination_field_id: int
    field_name: str
    field_type: str
    description: str
    overall_score: float
    exact_match_score: float
    synonym_match_score: float
    metadata_similarity_score: float
    type_compatibility_score: float


class RetrievalEngine:
    """
    Retrieval Engine that reduces search space before LLM processing.
    
    Retrieval Pipeline:
    1. Exact field name matching
    2. Synonym matching (business terminology)
    3. Metadata similarity (AI-generated descriptions)
    4. Data type compatibility
    5. Field length compatibility
    """

    def __init__(self, db: Session):
        self.db = db
        self.min_candidates = 5  # Always return top 5 candidates

    def retrieve_candidates(
        self, 
        source_field: SourceField, 
        destination_dataset_id: int,
        top_k: int = 5
    ) -> List[RetrievalCandidate]:
        """
        Retrieve top K candidate destination fields for a source field.
        
        Args:
            source_field: The source field to map
            destination_dataset_id: The destination dataset to search in
            top_k: Number of top candidates to return (default 5)
            
        Returns:
            List of RetrievalCandidate objects ranked by overall score
        """
        
        # Get all destination fields from the dataset
        destination_fields = self.db.query(DestinationField).filter(
            DestinationField.dataset_id == destination_dataset_id
        ).all()

        if not destination_fields:
            return []

        # Calculate scores for each destination field
        candidates = []
        for dest_field in destination_fields:
            scores = self._calculate_scores(source_field, dest_field)
            
            # Calculate weighted overall score
            overall_score = (
                scores["exact_match"] * 0.35 +
                scores["synonym_match"] * 0.25 +
                scores["metadata_similarity"] * 0.25 +
                scores["type_compatibility"] * 0.10 +
                scores["length_compatibility"] * 0.05
            )

            candidate = RetrievalCandidate(
                destination_field_id=dest_field.id,
                field_name=dest_field.field_name,
                field_type=dest_field.field_type,
                description=dest_field.description or "",
                overall_score=overall_score,
                exact_match_score=scores["exact_match"],
                synonym_match_score=scores["synonym_match"],
                metadata_similarity_score=scores["metadata_similarity"],
                type_compatibility_score=scores["type_compatibility"]
            )
            candidates.append(candidate)

        # Sort by overall score and return top K
        candidates.sort(key=lambda x: x.overall_score, reverse=True)
        return candidates[:top_k]

    def _calculate_scores(self, source_field: SourceField, dest_field: DestinationField) -> Dict[str, float]:
        """Calculate individual matching scores"""
        
        scores = {
            "exact_match": self._exact_name_match(source_field.field_name, dest_field.field_name),
            "synonym_match": self._synonym_match(source_field, dest_field),
            "metadata_similarity": self._metadata_similarity(source_field, dest_field),
            "type_compatibility": self._type_compatibility(source_field, dest_field),
            "length_compatibility": self._length_compatibility(source_field, dest_field)
        }
        
        return scores

    def _exact_name_match(self, source_name: str, dest_name: str) -> float:
        """
        Score exact field name matching.
        Handles case-insensitive and common naming conventions.
        """
        source_normalized = self._normalize_field_name(source_name)
        dest_normalized = self._normalize_field_name(dest_name)

        # Exact match
        if source_normalized == dest_normalized:
            return 1.0

        # Substring match (one contains the other)
        if source_normalized in dest_normalized or dest_normalized in source_normalized:
            return 0.7

        # Similarity ratio using sequence matching
        ratio = SequenceMatcher(None, source_normalized, dest_normalized).ratio()
        return max(0, ratio * 0.8)  # Cap at 0.8 for partial matches

    def _synonym_match(self, source_field: SourceField, dest_field: DestinationField) -> float:
        """
        Score matching against business terminology synonyms.
        """
        if not dest_field.synonyms:
            return 0.0

        source_normalized = self._normalize_field_name(source_field.field_name)
        best_match = 0.0

        for synonym in dest_field.synonyms:
            synonym_normalized = self._normalize_field_name(synonym)
            
            # Exact synonym match
            if source_normalized == synonym_normalized:
                return 1.0

            # Partial synonym match
            if source_normalized in synonym_normalized or synonym_normalized in source_normalized:
                best_match = max(best_match, 0.8)
            else:
                # Similarity ratio for synonyms
                ratio = SequenceMatcher(None, source_normalized, synonym_normalized).ratio()
                best_match = max(best_match, ratio * 0.7)

        return best_match

    def _metadata_similarity(self, source_field: SourceField, dest_field: DestinationField) -> float:
        """
        Score similarity between AI-generated metadata descriptions.
        """
        # Get metadata for source field
        metadata = self.db.query(FieldMetadata).filter(
            FieldMetadata.source_field_id == source_field.id
        ).first()

        if not metadata or not metadata.ai_generated_description:
            return 0.0

        source_desc = metadata.ai_generated_description.lower()
        dest_desc = (dest_field.description or "").lower()
        
        if not dest_desc:
            return 0.0

        # Calculate similarity using sequence matching
        ratio = SequenceMatcher(None, source_desc, dest_desc).ratio()
        return ratio * 0.9  # Weight down to 0.9 max since descriptions are longer

    def _type_compatibility(self, source_field: SourceField, dest_field: DestinationField) -> float:
        """
        Score data type compatibility between source and destination.
        """
        source_type = self._normalize_type(source_field.field_type or "")
        dest_type = self._normalize_type(dest_field.field_type or "")

        # Direct type match
        if source_type == dest_type:
            return 1.0

        # Compatible types
        compatible_groups = {
            "text": ["string", "varchar", "text", "char"],
            "numeric": ["int", "integer", "float", "decimal", "double", "numeric"],
            "date": ["date", "datetime", "timestamp"],
            "bool": ["boolean", "bit"]
        }

        for group, types in compatible_groups.items():
            if source_type in types and dest_type in types:
                return 0.8  # Compatible types
                
        return 0.2  # Different types, but possible

    def _length_compatibility(self, source_field: SourceField, dest_field: DestinationField) -> float:
        """
        Score field length compatibility.
        Destination field should be equal or larger than source.
        """
        if source_field.field_length is None or dest_field.field_length is None:
            return 0.5  # Unknown lengths

        if dest_field.field_length >= source_field.field_length:
            return 1.0
        
        # Destination is smaller - risky but possible
        ratio = dest_field.field_length / source_field.field_length
        return max(0.3, ratio)

    def _normalize_field_name(self, name: str) -> str:
        """Normalize field name for comparison"""
        # Convert to lowercase
        name = name.lower()
        # Remove underscores and replace with space
        name = name.replace("_", " ")
        # Remove special characters
        name = re.sub(r"[^a-z0-9\s]", "", name)
        # Remove extra whitespace
        name = " ".join(name.split())
        return name

    def _normalize_type(self, field_type: str) -> str:
        """Normalize data type for comparison"""
        field_type = field_type.lower().strip()
        # Handle variations
        if "varchar" in field_type or "char" in field_type:
            return "varchar"
        if "int" in field_type:
            return "int"
        if "decimal" in field_type or "numeric" in field_type or "float" in field_type:
            return "decimal"
        if "date" in field_type or "time" in field_type:
            return "date"
        return field_type
