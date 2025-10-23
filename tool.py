try:
    import asyncio
    loop = asyncio.get_event_loop()
    if hasattr(loop, '_nest_patched') or 'IPython' in str(type(loop)):
        import nest_asyncio
        nest_asyncio.apply()
except:
    pass

import os
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.schema.document import Document
from langchain_community.utilities import GoogleSerperAPIWrapper
import re
import json

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("FATAL ERROR: GOOGLE_API_KEY not found in .env file.")
if not SERPER_API_KEY:
    raise ValueError("FATAL ERROR: SERPER_API_KEY not found in .env file.")

try:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=GOOGLE_API_KEY,
        temperature=0.7
    )

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=GOOGLE_API_KEY
    )
except Exception as e:
    raise RuntimeError(f"Failed to initialize Google AI services. Please check your GOOGLE_API_KEY. Error: {e}")

def generate_probing_questions(interest_text: str) -> list[str]:
    prompt = PromptTemplate(
        input_variables=["interest_text"],
        template="""Based on the user's initial interest description: "{interest_text}",
        generate 3-4 short, specific questions to better understand their preferences.
        Focus on aspects like:
        - Specific sub-topics or companies.
        - Preferred regions or markets (e.g., US, Europe, Asia).
        - Types of news (e.g., product launches, financial results, policy changes).

        Return ONLY a JSON array of strings. For example:
        ["What specific companies are you interested in?", "Are you focused on consumer products or enterprise solutions?"]

        Do not include any other text or explanation.

        QUESTIONS:
        """
    )
    
    try:
        # Use invoke instead of run
        response = llm.invoke(prompt.format(interest_text=interest_text))
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # Try to extract JSON array from response
        json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
        if json_match:
            questions = json.loads(json_match.group())
            if isinstance(questions, list) and all(isinstance(q, str) for q in questions):
                return questions
    except Exception as e:
        print(f"Error generating probing questions: {e}")
    
    # Fallback questions if parsing fails
    return [
        "Could you be more specific about the topics?",
        "Are there any particular companies or people to follow?",
        "Which regions are you most interested in?"
    ]


def summarize_user_profile(initial_interest: str, answers: dict) -> str:
    answers_str = "\n".join([f"- {q}: {a}" for q, a in answers.items() if a and a.strip()])
    prompt = PromptTemplate(
        input_variables=["initial_interest", "answers_str"],
        template="""Create a concise, one-paragraph summary of a user's news preferences.
        This summary will be used to generate keywords for a news API.

        User's initial interest: "{initial_interest}"
        User's answers to clarifying questions:
        {answers_str}

        Synthesize this information into a clear profile summary.
        For example: "The user is interested in the latest AI developments, specifically focusing on
        Nvidia and Google's recent product launches and financial performance in the US market."

        PROFILE SUMMARY:
        """
    )
    
    try:
        # Use invoke instead of run
        response = llm.invoke(prompt.format(initial_interest=initial_interest, answers_str=answers_str))
        summary = response.content if hasattr(response, 'content') else str(response)
        return summary.strip()
    except Exception as e:
        print(f"Error generating profile summary: {e}")
        return initial_interest  # Fallback to original interest


def get_personalized_news(profile_summary: str, target_language: str) -> list[dict]:
    query_gen_prompt = PromptTemplate(
        input_variables=["profile_summary"],
        template="""Based on this user profile: "{profile_summary}",
        generate 3 diverse and specific keywords or short phrases for a news search.
        Return ONLY a JSON array of strings.

        Example: ["Nvidia AI developments", "latest generative AI research", "Google AI product launches in Europe"]

        Do not include any other text or explanation.

        KEYWORDS:
        """
    )
    
    try:
        # Use invoke instead of run
        response = llm.invoke(query_gen_prompt.format(profile_summary=profile_summary))
        queries_str = response.content if hasattr(response, 'content') else str(response)
        
        # Try to extract JSON array from response
        json_match = re.search(r'\[.*?\]', queries_str, re.DOTALL)
        if json_match:
            queries = json.loads(json_match.group())
            if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                pass  # queries is valid
            else:
                raise ValueError("Invalid query format")
        else:
            raise ValueError("No JSON array found in response")
    except Exception as e:
        print(f"Error generating search queries: {e}")
        queries = [profile_summary]  # Fallback to profile summary

    # Ensure we have the profile summary as a fallback query
    if profile_summary not in queries:
        queries.append(profile_summary)

    all_articles = []
    seen_urls = set()

    try:
        # Initialize search with proper parameters
        search = GoogleSerperAPIWrapper(
            type="news", 
            serper_api_key=SERPER_API_KEY, 
            k=5  # Use k instead of num for newer versions
        )
    except Exception as e:
        print(f"Failed to initialize GoogleSerperAPIWrapper: {e}")
        return []

    for query in queries[:4]:  # Limit to 4 queries to avoid rate limits
        print(f"Searching for news with query: '{query}'")
        try:
            results = search.results(query)
            
            if "news" in results and results["news"]:
                for article in results["news"]:
                    link = article.get("link", "")
                    if link and link not in seen_urls:
                        all_articles.append(article)
                        seen_urls.add(link)
            else:
                print(f"No news found in API response for query: '{query}'")

        except Exception as e:
            print(f"Error fetching or parsing news for query '{query}': {e}")
            continue

    if not all_articles:
        print("No news found after trying all queries.")
        return []

    news_items = []
    summarization_prompt = PromptTemplate(
        input_variables=["article_description", "target_language"],
        template="""Summarize the following news article description in 3-4 sentences.
        The tone should be neutral and informative.
        Translate the final summary into the language with the ISO 639-1 code: '{target_language}'.

        ARTICLE DESCRIPTION:
        "{article_description}"

        SUMMARY:
        """
    )

    for article in all_articles:
        description = article.get("snippet", article.get("title", ""))

        if not description or description.strip() == "" or "[Removed]" in description:
            continue

        try:
            # Use invoke instead of run
            response = llm.invoke(summarization_prompt.format(
                article_description=description, 
                target_language=target_language
            ))
            summary = response.content if hasattr(response, 'content') else str(response)
            
            news_items.append({
                "title": article.get("title", "No Title"),
                "link": article.get("link", "#"),
                "source": article.get("source", "Unknown"),
                "summary": summary.strip(),
                "snippet": description
            })
            
            # Stop once we have 4 successfully summarized articles
            if len(news_items) >= 4:
                break
                
        except Exception as e:
            print(f"Error summarizing article: {e}")
            continue

    return news_items


def query_news_feed(question: str, news_articles: list[dict], target_language: str) -> str:
    if not news_articles:
        return "The news feed hasn't been generated yet. Please generate the news first."

    try:
        # Create documents from news articles
        documents = [
            Document(
                page_content=f"Title: {article['title']}\nSummary: {article['summary']}",
                metadata={"source": article['source'], "link": article['link']}
            ) for article in news_articles
        ]

        # Create vector store with specific configuration to avoid tenant issues
        vector_store = Chroma.from_documents(
            documents, 
            embeddings,
            collection_name=f"news_collection_{len(documents)}",  # Unique collection name
            persist_directory=None  # Use in-memory storage
        )
        
        # Adjust k based on available documents
        max_k = min(3, len(documents))
        retriever = vector_store.as_retriever(search_kwargs={"k": max_k})
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever
        )

        prompt = f"""Based on the provided news context, answer the following question.
        Provide the answer in the language with the ISO 639-1 code: '{target_language}'.
        If the information is not available in the context, say so clearly.

        Question: "{question}"

        Answer:
        """

        # Use invoke instead of run
        response = qa_chain.invoke({"query": prompt})
        answer = response.get("result", "I couldn't find relevant information in the news feed.")
        return answer
        
    except Exception as e:
        print(f"Error in query_news_feed: {e}")
        # Fallback to simple text matching if vector search fails
        return fallback_text_search(question, news_articles, target_language)


def fallback_text_search(question: str, news_articles: list[dict], target_language: str) -> str:
    """Fallback method for answering questions when vector search fails"""
    try:
        # Create a context string from all articles
        context = "\n\n".join([
            f"Article {i+1}: {article['title']}\nSummary: {article['summary']}"
            for i, article in enumerate(news_articles)
        ])
        
        prompt = f"""Based on the following news articles, answer the question.
        Provide the answer in the language with the ISO 639-1 code: '{target_language}'.
        If the information is not available in the articles, say so clearly.

        NEWS ARTICLES:
        {context}

        Question: "{question}"

        Answer:
        """
        
        response = llm.invoke(prompt)
        answer = response.content if hasattr(response, 'content') else str(response)
        return answer.strip()
        
    except Exception as e:
        print(f"Error in fallback text search: {e}")
        return f"I encountered an error while searching for information about your question. Please try rephrasing or check if the news feed loaded correctly."
