"""
AI Service: Handles LLM calls for field mapping decisions
Uses the Retrieval Engine to narrow candidates before LLM
"""

import json
from typing import Optional, List, Dict, Any
import httpx
from sqlalchemy.orm import Session
from models import SourceField, DestinationField, FieldMapping, MappingStatus
from retrieval_engine import RetrievalEngine, RetrievalCandidate


class AIService:
    """Service for AI-powered field mapping using LLM"""

    def __init__(self, openrouter_api_key: str, openrouter_base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = openrouter_api_key
        self.base_url = openrouter_base_url
        self.model = "grok-2-1212"  # Can be changed to other models

    def map_source_field(
        self,
        db: Session,
        source_field: SourceField,
        destination_dataset_id: int,
        project_id: int
    ) -> Dict[str, Any]:
        """
        Map a source field to destination field using Retrieval Engine + LLM.
        
        Steps:
        1. Use Retrieval Engine to get Top 5 candidates
        2. Pass only Top 5 to LLM for decision
        3. Store results in database
        
        Returns:
            Dict with mapping result, confidence score, and retrieval candidates
        """
        
        # Step 1: Retrieval Engine - get top 5 candidates
        retrieval_engine = RetrievalEngine(db)
        candidates = retrieval_engine.retrieve_candidates(
            source_field, 
            destination_dataset_id,
            top_k=5
        )

        if not candidates:
            return {
                "success": False,
                "error": "No destination fields found",
                "source_field_id": source_field.id
            }

        # Step 2: Prepare candidates for LLM
        candidates_text = self._format_candidates_for_llm(candidates)

        # Step 3: Call LLM with limited candidates
        llm_response = self._call_llm_for_mapping(source_field, candidates_text)

        if not llm_response["success"]:
            return llm_response

        # Step 4: Parse LLM response
        best_match_id = llm_response["destination_field_id"]
        confidence_score = llm_response["confidence"]

        # Step 5: Store mapping in database
        mapping = self._create_or_update_mapping(
            db,
            project_id,
            source_field.id,
            best_match_id,
            candidates,
            confidence_score
        )

        return {
            "success": True,
            "mapping_id": mapping.id,
            "source_field_id": source_field.id,
            "destination_field_id": best_match_id,
            "confidence_score": confidence_score,
            "retrieval_candidates": [
                {
                    "id": c.destination_field_id,
                    "name": c.field_name,
                    "type": c.field_type,
                    "overall_score": round(c.overall_score, 3),
                    "description": c.description
                }
                for c in candidates
            ]
        }

    def _format_candidates_for_llm(self, candidates: List[RetrievalCandidate]) -> str:
        """Format retrieval candidates into a readable prompt for LLM"""
        
        formatted = "Candidate destination fields:\n\n"
        for i, candidate in enumerate(candidates, 1):
            formatted += f"{i}. {candidate.field_name}\n"
            formatted += f"   Type: {candidate.field_type}\n"
            formatted += f"   Description: {candidate.description}\n"
            formatted += f"   Retrieval Score: {candidate.overall_score:.2%}\n\n"
        
        return formatted

    def _call_llm_for_mapping(self, source_field: SourceField, candidates_text: str) -> Dict[str, Any]:
        """Call LLM to make final mapping decision from Top 5 candidates"""
        
        prompt = f"""
You are an expert ERP data mapping specialist. Your task is to map a source field to the best matching destination field.

SOURCE FIELD:
- Name: {source_field.field_name}
- Type: {source_field.field_type}
- Length: {source_field.field_length or 'Unknown'}
- Description: {source_field.description or 'Not provided'}
- Business Meaning: {source_field.business_meaning or 'Not provided'}

{candidates_text}

Based on the source field properties and the candidate destination fields above, select the BEST matching destination field.

Respond in JSON format with the following structure:
{{
    "selected_field_index": <1-5>,
    "confidence_score": <0.0-1.0>,
    "reasoning": "<brief explanation>",
    "alternative_matches": [<list of alternative field indices if any>]
}}

Make sure to return valid JSON only. The selected_field_index must correspond to the numbering in the candidate list (1-5).
"""

        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": 500
                    },
                    timeout=30.0
                )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"LLM API error: {response.status_code}",
                    "details": response.text
                }

            response_data = response.json()
            
            if not response_data.get("choices"):
                return {
                    "success": False,
                    "error": "Invalid LLM response format"
                }

            # Parse LLM response
            content = response_data["choices"][0]["message"]["content"]
            llm_result = json.loads(content)

            # Extract selected field index (1-5)
            field_index = llm_result.get("selected_field_index", 1)
            confidence = llm_result.get("confidence_score", 0.5)

            return {
                "success": True,
                "destination_field_id": field_index,  # Will be mapped to actual field ID
                "confidence": confidence,
                "reasoning": llm_result.get("reasoning", "")
            }

        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Failed to parse LLM response as JSON"
            }
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "LLM API request timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _create_or_update_mapping(
        self,
        db: Session,
        project_id: int,
        source_field_id: int,
        ai_suggested_dest_field_id: int,
        retrieval_candidates: List[RetrievalCandidate],
        confidence_score: float
    ) -> FieldMapping:
        """Create or update a field mapping record"""
        
        # Check if mapping already exists
        existing = db.query(FieldMapping).filter(
            FieldMapping.project_id == project_id,
            FieldMapping.source_field_id == source_field_id
        ).first()

        candidates_data = [
            {
                "id": c.destination_field_id,
                "name": c.field_name,
                "score": c.overall_score
            }
            for c in retrieval_candidates
        ]

        if existing:
            existing.ai_suggested_destination_id = ai_suggested_dest_field_id
            existing.ai_confidence_score = confidence_score
            existing.retrieval_candidates = candidates_data
            existing.status = MappingStatus.SUGGESTED
            mapping = existing
        else:
            mapping = FieldMapping(
                project_id=project_id,
                source_field_id=source_field_id,
                destination_field_id=ai_suggested_dest_field_id,
                ai_suggested_destination_id=ai_suggested_dest_field_id,
                ai_confidence_score=confidence_score,
                retrieval_candidates=candidates_data,
                status=MappingStatus.SUGGESTED
            )
            db.add(mapping)

        db.commit()
        db.refresh(mapping)
        return mapping
