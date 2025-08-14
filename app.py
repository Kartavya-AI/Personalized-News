import streamlit as st
import tool

# Set page configuration
st.set_page_config(
    page_title="Personalized News Agent",
    page_icon="📰",
    layout="wide"
)

# Initialize session state variables
if 'stage' not in st.session_state:
    st.session_state.stage = 'initial_input'
if 'initial_interest' not in st.session_state:
    st.session_state.initial_interest = ""
if 'probing_questions' not in st.session_state:
    st.session_state.probing_questions = []
if 'probing_answers' not in st.session_state:
    st.session_state.probing_answers = {}
if 'profile_summary' not in st.session_state:
    st.session_state.profile_summary = ""
if 'news_feed' not in st.session_state:
    st.session_state.news_feed = []
# Hardcode language to English
if 'language_code' not in st.session_state:
    st.session_state.language_code = "en"

# --- SIDEBAR ---
with st.sidebar:
    st.title("📰 Personalized News Agent")
    st.markdown("Your daily news, tailored to your interests.")
    st.divider()
    
    # Display current stage for debugging (optional)
    st.caption(f"Current stage: {st.session_state.stage}")
    
    # Start Over button
    if st.button("🔄 Start Over"):
        # Clear all session state
        keys_to_clear = ['stage', 'initial_interest', 'probing_questions', 
                        'probing_answers', 'profile_summary', 'news_feed']
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        # Reset to initial values
        st.session_state.stage = 'initial_input'
        st.session_state.initial_interest = ""
        st.session_state.probing_questions = []
        st.session_state.probing_answers = {}
        st.session_state.profile_summary = ""
        st.session_state.news_feed = []
        st.session_state.language_code = "en"
        
        st.rerun()


# --- MAIN PAGE UI LOGIC ---

# STAGE 0: Initial Input
if st.session_state.stage == 'initial_input':
    st.header("Step 1: Tell Us Your Interests")
    st.markdown("Describe what kind of news you're interested in. Be as general or specific as you like.")

    interest_input = st.text_area(
        "Your interests:", 
        placeholder="For example: 'I'm interested in AI, startups, and electric vehicles.'", 
        height=150,
        value=st.session_state.initial_interest
    )

    if st.button("Create My News Feed", type="primary"):
        if interest_input.strip():
            st.session_state.initial_interest = interest_input.strip()
            
            with st.spinner("Analyzing your interests..."):
                try:
                    st.session_state.probing_questions = tool.generate_probing_questions(interest_input)
                except Exception as e:
                    st.error(f"An error occurred while generating questions: {e}")
                    st.session_state.probing_questions = []

            # Improved Flow: Skip probing if no questions are generated or if they're generic
            if (st.session_state.probing_questions and 
                len(st.session_state.probing_questions) > 0 and
                not all("Could you be more specific" in q for q in st.session_state.probing_questions)):
                st.session_state.stage = 'probing_stage'
                st.success("Great! Let's refine your profile with a few questions.")
            else:
                st.info("Proceeding with your description. Generating your news feed...")
                st.session_state.probing_answers = {}
                st.session_state.stage = 'news_display'
            st.rerun()
        else:
            st.warning("Please describe your interests first.")

# STAGE 1: Probing Questions
elif st.session_state.stage == 'probing_stage':
    st.header("Step 2: Let's Refine Your Profile")
    st.markdown("To give you the best news, please answer a few clarifying questions.")
    
    # Display the user's initial interest for context
    with st.expander("Your initial interests", expanded=False):
        st.write(st.session_state.initial_interest)

    # Create a form for better UX
    with st.form("probing_questions_form"):
        answers = {}
        for i, question in enumerate(st.session_state.probing_questions):
            answers[question] = st.text_input(
                question, 
                key=f"ans_{i}",
                placeholder="Optional - leave blank if not applicable"
            )
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.form_submit_button("Finalize Profile", type="primary"):
                st.session_state.probing_answers = {q: a for q, a in answers.items() if a.strip()}
                st.session_state.stage = 'news_display'
                st.rerun()
        
        with col2:
            if st.form_submit_button("Skip Questions"):
                st.session_state.probing_answers = {}
                st.session_state.stage = 'news_display'
                st.rerun()

# STAGE 2: News Display and Q&A
elif st.session_state.stage == 'news_display':
    st.header("Your Personalized News Feed")

    try:
        # Generate profile summary if it doesn't exist yet
        if not st.session_state.profile_summary:
            with st.spinner("Creating your personalized profile..."):
                st.session_state.profile_summary = tool.summarize_user_profile(
                    st.session_state.initial_interest,
                    st.session_state.probing_answers
                )

        # Show profile summary
        with st.expander("👤 Your News Profile Summary", expanded=False):
            st.write(st.session_state.profile_summary)

        # Generate news feed if it doesn't exist yet
        if not st.session_state.news_feed:
            with st.spinner("🔍 Curating your news... Please wait, this may take a moment."):
                try:
                    st.session_state.news_feed = tool.get_personalized_news(
                        st.session_state.profile_summary,
                        st.session_state.language_code
                    )
                except Exception as e:
                    st.error(f"Error generating news feed: {e}")
                    st.session_state.news_feed = []

        # Display the generated news feed
        if st.session_state.news_feed:
            st.success(f"Found {len(st.session_state.news_feed)} personalized articles for you!")
            
            for i, item in enumerate(st.session_state.news_feed, 1):
                with st.container():
                    st.subheader(f"{i}. {item['title']}")
                    
                    # Create columns for source and link
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.markdown(f"**Source:** {item['source']}")
                    with col2:
                        st.markdown(f"[Read Full Article]({item['link']})")
                    
                    st.write(item['summary'])
                    st.divider()
            
            # Conversational Q&A Section
            st.header("💬 Ask About Your News")
            st.markdown("Have questions about the articles above? Ask away!")

            question = st.text_input(
                "Your question:", 
                placeholder="e.g., What are the key developments in AI this week?",
                key="news_question"
            )
            
            if st.button("Ask", type="secondary"):
                if question.strip():
                    with st.spinner("🔍 Searching for an answer..."):
                        try:
                            answer = tool.query_news_feed(
                                question,
                                st.session_state.news_feed,
                                st.session_state.language_code
                            )
                            st.success("**Answer:**")
                            st.write(answer)
                        except Exception as e:
                            st.error(f"An error occurred while searching for the answer: {e}")
                else:
                    st.warning("Please enter a question.")
                    
        else:
            st.warning("⚠️ Could not fetch news based on your profile. This might be due to:")
            st.markdown("""
            - API rate limits
            - Network connectivity issues
            - No recent news matching your specific interests
            """)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Try Again", type="primary"):
                    st.session_state.news_feed = []  # Clear and retry
                    st.rerun()
            with col2:
                if st.button("Refine Interests", type="secondary"):
                    st.session_state.stage = 'initial_input'
                    st.rerun()

    except Exception as e:
        st.error(f"A critical error occurred: {e}")
        st.markdown("**Troubleshooting steps:**")
        st.markdown("""
        1. Check your internet connection
        2. Verify API keys in your .env file
        3. Try starting over with different interests
        """)
        
        if st.button("🔄 Start Over", key="error_restart"):
            # Clear all session state
            for key in list(st.session_state.keys()):
                if key != 'language_code':
                    del st.session_state[key]
            st.session_state.stage = 'initial_input'
            st.rerun()

# Unknown stage fallback
else:
    st.error(f"Unknown stage: {st.session_state.stage}")
    st.session_state.stage = 'initial_input'
    st.rerun()