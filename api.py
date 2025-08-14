import os
import logging
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

# Import the tool functions
from tool import (
    generate_probing_questions,
    summarize_user_profile,
    get_personalized_news,
    query_news_feed
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for request/response validation
class InterestRequest(BaseModel):
    interest_text: str = Field(..., min_length=1, max_length=500, description="User's initial interest description")

class QuestionResponse(BaseModel):
    questions: List[str] = Field(..., description="List of probing questions")

class ProfileRequest(BaseModel):
    initial_interest: str = Field(..., min_length=1, max_length=500, description="User's initial interest")
    answers: Dict[str, str] = Field(..., description="Dictionary of question-answer pairs")

class ProfileResponse(BaseModel):
    profile_summary: str = Field(..., description="Generated user profile summary")

class NewsRequest(BaseModel):
    profile_summary: str = Field(..., min_length=1, max_length=1000, description="User profile summary")
    target_language: str = Field(default="en", description="Target language code (ISO 639-1)")
    
    @validator('target_language')
    def validate_language_code(cls, v):
        # Basic validation for common language codes
        valid_codes = ['en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'ru', 'ja', 'ko', 'zh', 'ar', 'hi']
        if v not in valid_codes:
            logger.warning(f"Language code '{v}' not in common codes list, but allowing it")
        return v

class NewsArticle(BaseModel):
    title: str
    link: str
    source: str
    summary: str
    snippet: str

class NewsResponse(BaseModel):
    articles: List[NewsArticle] = Field(..., description="List of personalized news articles")
    profile_summary: str = Field(..., description="Profile summary used for news generation")

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Question about the news feed")
    target_language: str = Field(default="en", description="Target language code (ISO 639-1)")
    
    @validator('target_language')
    def validate_language_code(cls, v):
        valid_codes = ['en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'ru', 'ja', 'ko', 'zh', 'ar', 'hi']
        if v not in valid_codes:
            logger.warning(f"Language code '{v}' not in common codes list, but allowing it")
        return v

class QueryResponse(BaseModel):
    answer: str = Field(..., description="Answer to the user's question")

class HealthResponse(BaseModel):
    status: str
    message: str

class ErrorResponse(BaseModel):
    error: str
    detail: str

# Global variable to store news articles for querying
news_articles_cache: Dict[str, List[dict]] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("Starting FastAPI application...")
    
    # Validate environment variables
    required_env_vars = ["GOOGLE_API_KEY", "SERPER_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        raise RuntimeError(f"Missing required environment variables: {missing_vars}")
    
    logger.info("All required environment variables are set")
    logger.info("FastAPI application started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down FastAPI application...")

# Initialize FastAPI app
app = FastAPI(
    title="Personalized News API",
    description="A production-ready API for generating personalized news feeds using LangChain and Google AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check"""
    return HealthResponse(status="healthy", message="Personalized News API is running")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        # Basic environment variable check
        required_vars = ["GOOGLE_API_KEY", "SERPER_API_KEY"]
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Missing environment variables: {missing_vars}"
            )
        
        return HealthResponse(status="healthy", message="All systems operational")
    
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )

@app.post("/generate-questions", response_model=QuestionResponse)
async def generate_questions_endpoint(request: InterestRequest):
    """Generate probing questions based on user's initial interest"""
    try:
        logger.info(f"Generating questions for interest: {request.interest_text[:50]}...")
        
        questions = generate_probing_questions(request.interest_text)
        
        if not questions or not isinstance(questions, list):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate valid questions"
            )
        
        logger.info(f"Generated {len(questions)} questions successfully")
        return QuestionResponse(questions=questions)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating questions"
        )

@app.post("/create-profile", response_model=ProfileResponse)
async def create_profile_endpoint(request: ProfileRequest):
    """Create user profile summary from initial interest and answers"""
    try:
        logger.info(f"Creating profile for interest: {request.initial_interest[:50]}...")
        
        profile_summary = summarize_user_profile(request.initial_interest, request.answers)
        
        if not profile_summary or profile_summary.strip() == "":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate valid profile summary"
            )
        
        logger.info("Profile summary created successfully")
        return ProfileResponse(profile_summary=profile_summary)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while creating profile"
        )

@app.post("/generate-news", response_model=NewsResponse)
async def generate_news_endpoint(request: NewsRequest):
    """Generate personalized news based on user profile"""
    try:
        logger.info(f"Generating news for profile: {request.profile_summary[:50]}...")
        
        articles = get_personalized_news(request.profile_summary, request.target_language)
        
        if not articles:
            logger.warning("No articles found for the given profile")
            return NewsResponse(
                articles=[],
                profile_summary=request.profile_summary
            )
        
        # Store articles in cache for querying (using profile summary as key)
        cache_key = f"{request.profile_summary}_{request.target_language}"
        news_articles_cache[cache_key] = articles
        
        # Convert to Pydantic models
        news_articles = [NewsArticle(**article) for article in articles]
        
        logger.info(f"Generated {len(news_articles)} articles successfully")
        return NewsResponse(
            articles=news_articles,
            profile_summary=request.profile_summary
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating news: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while generating news"
        )

@app.post("/query-news", response_model=QueryResponse)
async def query_news_endpoint(request: QueryRequest):
    """Query the news feed with a specific question"""
    try:
        logger.info(f"Querying news with question: {request.question[:50]}...")
        
        # For simplicity, we'll use the most recent cache entry
        # In a production system, you might want to implement a more sophisticated caching strategy
        if not news_articles_cache:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No news articles available. Please generate news first using /generate-news endpoint."
            )
        
        # Get the most recent articles (you might want to implement a better strategy)
        most_recent_key = max(news_articles_cache.keys(), key=lambda k: len(news_articles_cache[k]))
        articles = news_articles_cache[most_recent_key]
        
        answer = query_news_feed(request.question, articles, request.target_language)
        
        if not answer or answer.strip() == "":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate valid answer"
            )
        
        logger.info("Query answered successfully")
        return QueryResponse(answer=answer)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying news: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error while querying news"
        )

class FullPipelineRequest(BaseModel):
    initial_interest: str = Field(..., min_length=1, max_length=500, description="User's initial interest")
    answers: Dict[str, str] = Field(..., description="Dictionary of question-answer pairs")
    target_language: str = Field(default="en", description="Target language code (ISO 639-1)")
    
    @validator('target_language')
    def validate_language_code(cls, v):
        valid_codes = ['en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'ru', 'ja', 'ko', 'zh', 'ar', 'hi']
        if v not in valid_codes:
            logger.warning(f"Language code '{v}' not in common codes list, but allowing it")
        return v

class FullPipelineResponse(BaseModel):
    profile_summary: str = Field(..., description="Generated user profile summary")
    articles: List[NewsArticle] = Field(..., description="List of personalized news articles")
    article_count: int = Field(..., description="Number of articles generated")

@app.post("/full-pipeline", response_model=FullPipelineResponse)
async def full_pipeline_endpoint(request: FullPipelineRequest):
    """Complete pipeline: create profile and generate news in one call"""
    try:
        logger.info(f"Running full pipeline for interest: {request.initial_interest[:50]}...")
        
        # Create profile
        profile_summary = summarize_user_profile(request.initial_interest, request.answers)
        
        # Generate news
        articles = get_personalized_news(profile_summary, request.target_language)
        
        # Cache articles
        cache_key = f"{profile_summary}_{request.target_language}"
        news_articles_cache[cache_key] = articles
        
        # Convert to response format
        news_articles = [NewsArticle(**article) for article in articles]
        
        logger.info(f"Full pipeline completed with {len(news_articles)} articles")
        
        return FullPipelineResponse(
            profile_summary=profile_summary,
            articles=news_articles,
            article_count=len(news_articles)
        )
    
    except Exception as e:
        logger.error(f"Error in full pipeline: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error in full pipeline"
        )

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "detail": str(exc.detail)}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """General exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": "An unexpected error occurred"}
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True
    )