import nest_asyncio
nest_asyncio.apply()

import os
import requests
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains.llm import LLMChain
from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.schema.document import Document

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("FATAL ERROR: GOOGLE_API_KEY not found in .env file.")
if not NEWS_API_KEY:
    raise ValueError("FATAL ERROR: NEWS_API_KEY not found in .env file.")

try:
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-pro",
        google_api_key=GOOGLE_API_KEY, 
        temperature=0.7,
        convert_system_message_to_human=True
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
        
        Return the questions as a Python list of strings. For example:
        ["What specific companies are you interested in?", "Are you focused on consumer products or enterprise solutions?"]
        
        QUESTIONS:
        """
    )
    chain = LLMChain(llm=llm, prompt=prompt)
    response = chain.run(interest_text)
    
    try:
        questions = eval(response)
        if isinstance(questions, list):
            return questions
    except:
        return ["Could you be more specific about the topics?", 
                "Are there any particular companies or people to follow?", 
                "Which regions are you most interested in?"]
    return []


def summarize_user_profile(initial_interest: str, answers: dict) -> str:
    answers_str = "\n".join([f"- {q}: {a}" for q, a in answers.items()])
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
    chain = LLMChain(llm=llm, prompt=prompt)
    summary = chain.run(initial_interest=initial_interest, answers_str=answers_str)
    return summary


def get_personalized_news(profile_summary: str, target_language: str) -> list[dict]:
    query_gen_prompt = PromptTemplate(
        input_variables=["profile_summary"],
        template="""Based on this user profile: "{profile_summary}", 
        generate 3 diverse and specific keywords or short phrases for a news API.
        The News API works best with concise keywords.
        Return the keywords as a Python list of strings.
        
        Example: ["Nvidia AI", "Generative AI research", "Google AI Europe"]

        KEYWORDS:
        """
    )
    query_chain = LLMChain(llm=llm, prompt=prompt)
    queries_str = query_chain.run(profile_summary)
    try:
        queries = eval(queries_str)
    except:
        queries = [profile_summary]

    all_articles = []
    
    for query in queries[:3]:
        url = f"https://newsapi.org/v2/everything?q={query}&apiKey={NEWS_API_KEY}&language=en&sortBy=relevancy&pageSize=3"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "ok":
                all_articles.extend(data.get("articles", []))
        except requests.exceptions.RequestException as e:
            print(f"Error fetching news for query '{query}': {e}")
            continue

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
    summarization_chain = LLMChain(llm=llm, prompt=summarization_prompt)

    seen_urls = set()
    for article in all_articles:
        if "url" in article and article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            description = article.get("description", article.get("title", ""))
            
            if not description or description.strip() == "" or "[Removed]" in description:
                continue

            summary = summarization_chain.run(article_description=description, target_language=target_language)
            news_items.append({
                "title": article.get("title", "No Title"),
                "link": article.get("url", "#"),
                "source": article.get("source", {}).get("name", "Unknown"),
                "summary": summary,
                "snippet": description
            })
        if len(news_items) >= 4:
            break

    return news_items


def query_news_feed(question: str, news_articles: list[dict], target_language: str) -> str:
    if not news_articles:
        return "The news feed hasn't been generated yet. Please generate the news first."

    documents = [
        Document(
            page_content=f"Title: {article['title']}\nSummary: {article['summary']}",
            metadata={"source": article['source'], "link": article['link']}
        ) for article in news_articles
    ]

    vector_store = Chroma.from_documents(documents, embeddings)
    qa_chain = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=vector_store.as_retriever()
    )

    prompt = f"""Based on the provided news context, answer the following question.
    Provide the answer in the language with the ISO 639-1 code: '{target_language}'.

    Question: "{question}"
    
    Answer:
    """
    
    response = qa_chain.run(prompt)
    return response