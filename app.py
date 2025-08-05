import streamlit as st
import tool

st.set_page_config(
    page_title="Personalized News Agent",
    page_icon="📰",
    layout="wide"
)

if 'stage' not in st.session_state:
    st.session_state.stage = 'initial_input'
if 'initial_interest' not in st.session_state:
    st.session_state.initial_interest = ""
if 'probing_questions' not in st.session_state:
    st.session_state.probing_questions = []
if 'Youtubes' not in st.session_state:
    st.session_state.Youtubes = {}
if 'profile_summary' not in st.session_state:
    st.session_state.profile_summary = ""
if 'news_feed' not in st.session_state:
    st.session_state.news_feed = []
if 'language_code' not in st.session_state:
    st.session_state.language_code = "en" 

# --- SIDEBAR ---
with st.sidebar:
    st.title("📰 Personalized News Agent")
    st.markdown("Your daily news, tailored to your interests.")
    
    languages = {
        "English": "en",
        "German": "de",
        "Hindi": "hi",
        "Tamil": "ta",
        "Malayalam": "ml",
        "Telugu": "te"
    }
    selected_lang_name = st.selectbox(
        "Select News Language",
        options=list(languages.keys()),
        index=list(languages.values()).index(st.session_state.language_code)
    )
    st.session_state.language_code = languages[selected_lang_name]

    st.divider()
    if st.button("🔄 Start Over"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# --- MAIN PAGE UI LOGIC ---
if st.session_state.stage == 'initial_input':
    st.header("Step 1: Tell Us Your Interests")
    st.markdown("Describe what kind of news you're interested in. Be as general or specific as you like.")
    
    interest_input = st.text_area("For example: 'I'm interested in AI, startups, and electric vehicles.'", height=150)

    if st.button("Create My News Feed", type="primary"):
        if interest_input:
            st.session_state.initial_interest = interest_input
            with st.spinner("Analyzing your interests..."):
                st.session_state.probing_questions = tool.generate_probing_questions(interest_input)
            st.session_state.stage = 'probing_stage'
            st.rerun()
        else:
            st.warning("Please describe your interests first.")

# STAGE 1: Probing Questions
elif st.session_state.stage == 'probing_stage':
    st.header("Step 2: Let's Refine Your Profile")
    st.markdown("To give you the best news, please answer a few clarifying questions.")
    
    answers = {}
    for i, question in enumerate(st.session_state.probing_questions):
        answers[question] = st.text_input(question, key=f"ans_{i}")

    if st.button("Finalize Profile", type="primary"):
        st.session_state.Youtubes = answers
        st.session_state.stage = 'news_display'
        st.rerun()

# STAGE 2: News Display and Q&A
elif st.session_state.stage == 'news_display':
    st.header("Your Personalized News Feed")
    
    # Generate profile summary and news feed if they don't exist yet
    if not st.session_state.profile_summary:
        with st.spinner("Creating your personalized profile..."):
            st.session_state.profile_summary = tool.summarize_user_profile(
                st.session_state.initial_interest,
                st.session_state.Youtubes
            )
    
    with st.expander("👤 Your News Profile Summary", expanded=False):
        st.write(st.session_state.profile_summary)

    if not st.session_state.news_feed:
        with st.spinner(f"Curating your news in {selected_lang_name}... Please wait, this may take a moment."):
            st.session_state.news_feed = tool.get_personalized_news(
                st.session_state.profile_summary,
                st.session_state.language_code
            )

    # Display the generated news feed
    if st.session_state.news_feed:
        for item in st.session_state.news_feed:
            st.subheader(item['title'])
            st.markdown(f"**Source:** {item['source']}")
            st.write(item['summary'])
            st.markdown(f"[Read Full Article]({item['link']})")
            st.divider()
    else:
        st.warning("Could not fetch news based on your profile. Try refining your interests or starting over.")

    # Conversational Q&A Section
    st.header("Talk to Your News Feed")
    st.markdown("Ask a question about the news articles presented above.")
    
    question = st.text_input("e.g., What happened with Nvidia this week?")
    if st.button("Ask"):
        if question:
            with st.spinner("Searching for an answer..."):
                answer = tool.query_news_feed(
                    question,
                    st.session_state.news_feed,
                    st.session_state.language_code
                )
                st.info(answer)
        else:
            st.warning("Please enter a question.")