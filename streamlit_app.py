import base64
import streamlit as st
import requests

API_URL = "http://127.0.0.1:8000/recommend"


def apply_theme(image_path):
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()
    PURPLE = "#7C4DFF"
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
        html, body, [class*="css"] {{ font-family: 'Poppins', sans-serif; }}

        /* 1. Full-viewport fixed background */
        [data-testid="stAppViewContainer"] {{
            background-image: linear-gradient(rgba(15,8,30,0.68), rgba(15,8,30,0.68)),
                               url("data:image/jpeg;base64,{encoded}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
        [data-testid="stHeader"] {{ background: rgba(0,0,0,0); }}

        /* 2. Frosted glass cards */
        [data-testid="stVerticalBlockBorderWrapper"],
        [data-testid="stForm"] {{
            background: rgba(255,255,255,0.82) !important;
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            border-radius: 22px !important;
            border: 1px solid rgba(255,255,255,0.4) !important;
            box-shadow: 0 8px 32px rgba(0,0,0,0.25);
            padding: 0.5rem;
        }}

        /* 3. Page title */
        .platter-title {{ color: #ffffff; font-size: 2.4rem; font-weight: 700; margin-bottom: 0; }}
        .platter-title span {{ color: {PURPLE}; }}

        /* FIX: tagline used to be low-contrast (faint white on light glass).
           Bumped to full white + a soft shadow so it's readable against
           both the dark background and the glass card underneath it. */
        .platter-caption {{
            color: #ffffff;
            font-size: 1.05rem;
            margin-top: 0.2rem;
            font-weight: 500;
            text-shadow: 0 1px 4px rgba(0,0,0,0.55);
        }}

        /* 4. Inputs -- soft glass fields with rounded corners */
        [data-testid="stTextInput"] input {{
            background: rgba(255,255,255,0.9);
            border-radius: 12px;
            border: 1px solid rgba(124,77,255,0.25);
        }}

        /* 5. Buttons -- purple, rounded, premium */
        .stButton > button, .stFormSubmitButton > button,
        [data-testid="stLinkButton"] a {{
            background: {PURPLE} !important;
            color: #ffffff !important;
            border-radius: 12px !important;
            border: none !important;
            font-weight: 600 !important;
            padding: 0.5rem 1.2rem !important;
            transition: transform 0.15s ease;
        }}
        .stButton > button:hover, .stFormSubmitButton > button:hover,
        [data-testid="stLinkButton"] a:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 14px rgba(124,77,255,0.45);
        }}

        /* 6. Info banners */
        [data-testid="stAlert"] {{
            background: rgba(124,77,255,0.12) !important;
            border-radius: 14px !important;
            backdrop-filter: blur(10px);
        }}

        /* 7. Progress bars */
        [data-testid="stProgress"] > div > div > div {{ background-color: {PURPLE} !important; }}

        /* 8. Metric numbers */
        [data-testid="stMetricValue"] {{ color: {PURPLE}; }}

        /* 9. Expanders */
        [data-testid="stExpander"] {{
            background: rgba(255,255,255,0.82) !important;
            backdrop-filter: blur(14px);
            border-radius: 18px !important;
            border: 1px solid rgba(255,255,255,0.4) !important;
        }}

        /* 10. FIX: checkbox used to be a plain default (red) box that
           clashed with the purple theme. `accent-color` re-colors native
           checkboxes/radios in all modern browsers with one line -- no
           need to fight Streamlit's internal SVG markup. */
        [data-testid="stCheckbox"] input[type="checkbox"] {{
            accent-color: {PURPLE};
            width: 18px;
            height: 18px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="PlatterMint", page_icon="🍽️", layout="centered")
apply_theme("assets/background.jpg")

st.markdown(
    """
    <div class="platter-title">🍽️ Platter<span>Mint</span></div>
    <div class="platter-caption">Your AI dining advisor --- not just a restaurant search</div>
    <br>
    """,
    unsafe_allow_html=True,
)

with st.form("query_form"):
    user_id = st.text_input("Your name / user ID", value="guest")

    
    location = st.text_input("Your location", value="Nashik", autocomplete="off")
    user_query = st.text_input(
        "What are you craving?",
        placeholder="e.g. cheap pizza near me / best south indian food / something sweet"
    )

    
    ask_if_unsure = st.checkbox(
        "Ask me before relaxing filters (human-in-the-loop)",
        value=True,
        help="If nothing matches perfectly, PlatterMint will pause and let you choose "
             "how to adjust --- instead of the AI silently deciding for you.",
    )

    submitted = st.form_submit_button("✨ Find restaurants")

# ---------------------------------------------------------------------------
# Small display helpers
# ---------------------------------------------------------------------------
def render_score_breakdown(breakdown):
    for item in breakdown:
        st.progress(
            item["earned"] / item["possible"] if item["possible"] else 0,
            text=f"{item['factor']}: {item['earned']}/{item['possible']}",
        )
        if item.get("note"):
            st.caption(f"ⓘ {item['note']}")


def render_restaurant_card(restaurant, is_top=False):
    stars = "⭐" * max(1, round(restaurant.get("rating", 0)))
    distance = f" • 📍 {restaurant['distance_km']} km away" if restaurant.get("distance_km") else ""
    with st.container(border=True):
        if is_top:
            st.markdown(f"### 🥇 AI Top Pick --- {restaurant.get('name')}")
            st.markdown(f"## {restaurant['match_score']}/100  ·  AI Match Score")
        else:
            st.markdown(f"**🍴 {restaurant.get('name')}**  ·  {restaurant['match_score']}/100")
        st.markdown(f"{stars} {restaurant.get('rating')} &nbsp;|&nbsp; {restaurant.get('price_display')}{distance}")

        if is_top:
            with st.expander("See the full score breakdown"):
                render_score_breakdown(restaurant["score_breakdown"])
            st.markdown("**Why we picked it:**")
            for r in restaurant.get("reasons", []):
                st.markdown(f"- ✅ {r}")
            st.markdown(f"**Confidence: {restaurant['confidence']}%**")
            for r in restaurant.get("confidence_reasons", []):
                st.caption(f"✓ {r}")
            col1, col2 = st.columns(2)
            with col1:
                st.link_button("📍 Open in Google Maps", restaurant["maps_url"], use_container_width=True)
            with col2:
                st.link_button("🧭 Directions", restaurant["directions_url"], use_container_width=True)
        else:
            st.caption(f"Why: {restaurant.get('reason')}")
            st.link_button("📍 View on Google Maps", restaurant["maps_url"])


def render_more_options(more_options):
    for r in more_options:
        st.markdown(
            f"- **{r['name']}** · {r['match_score']}/100 · ⭐ {r.get('rating')} · "
            f"{r.get('price_display')} · [View on Maps]({r['maps_url']})"
        )


def fetch_recommendation(relaxation_choice=None):
    """Calls the backend. Reuses the last-submitted query, optionally with the person's choice attached."""
    q = st.session_state["last_query"]
    response = requests.post(API_URL, json={
        "user_id": q["user_id"],
        "user_query": q["user_query"],
        "location": q["location"],
        "ask_if_unsure": q["ask_if_unsure"],
        "relaxation_choice": relaxation_choice,
    })
    return response.json()


if submitted:
    if not user_query.strip():
        st.warning("Please type what you're looking for.")
    else:
        st.session_state["last_query"] = {
            "user_id": user_id, "user_query": user_query,
            "location": location, "ask_if_unsure": ask_if_unsure,
        }
        st.session_state["api_response"] = None  # force a fresh fetch below

if "last_query" in st.session_state:
    try:
        if st.session_state.get("api_response") is None:
            with st.spinner("Agents are working..."):
                st.session_state["api_response"] = fetch_recommendation()

        data = st.session_state["api_response"]

        # ---- PAUSED: the Filter agent wants a human decision ----
        if data.get("needs_human_input"):
            st.warning("🙋 I couldn't find a perfect match for every filter. What would you like me to do?")
            for option in data["relaxation_options"]:
                if st.button(
                    f"{option['label']}  ·  {option['preview_count']} results",
                    key=f"opt_{option['key']}",
                    use_container_width=True,
                ):
                    with st.spinner("Applying your choice..."):
                        st.session_state["api_response"] = fetch_recommendation(relaxation_choice=option["key"])
                    st.rerun()

            with st.expander("🤖 See how the agents worked through this"):
                for step in data.get("agent_trace", []):
                    st.markdown(f"- {step}")

        # ---- NORMAL: full recommendation ready ----
        else:
            if data.get("welcome_message"):
                st.info(data["welcome_message"])
            if data.get("relaxed_by_human"):
                st.success("🙋 You chose how to adjust the filters --- here's what matched.")
            if data.get("intro_line"):
                st.markdown(f"*{data['intro_line']}*")

            dash = data.get("decision_dashboard")
            if dash and dash.get("winner"):
                with st.container(border=True):
                    st.markdown("#### 🧠 AI Decision Summary")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Found", dash["found_count"])
                    c2.metric("Rejected", dash["rejected_count"])
                    c3.metric("Compared", dash["compared_count"])
                    st.markdown(f"**Winner:** {dash['winner']} --- {dash['score']}/100, {dash['confidence']}% confidence")

            st.divider()

            top_pick = data.get("top_pick")
            if top_pick:
                render_restaurant_card(top_pick, is_top=True)
            else:
                st.warning(data.get("final_answer", "No matches found."))

            hist = data.get("history_comparison")
            if hist:
                st.markdown("#### 🧠 What changed because of your history")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Without your history**")
                    st.write(f"{hist['without_history']['name']} --- {hist['without_history']['price_display']}")
                with col2:
                    st.markdown("**Using your preferences**")
                    st.write(f"{hist['with_history']['name']} --- {hist['with_history']['price_display']}")
                st.caption(hist["reason"])

            alternatives = data.get("alternatives") or []
            if alternatives:
                st.markdown("#### Other options the AI considered")
                for alt in alternatives:
                    render_restaurant_card(alt)

            # FIX (#10): ranks 4-8, previously discarded entirely
            more_options = data.get("more_options") or []
            if more_options:
                with st.expander(f"See {len(more_options)} more restaurants the AI compared"):
                    render_more_options(more_options)

            st.divider()

            constraint_status = data.get("constraint_status")
            if constraint_status:
                with st.expander("⚖️ AI Trade-off Analysis --- what was kept vs. adjusted"):
                    for label, value in constraint_status.items():
                        st.markdown(f"**{label.title()}:** {value}")

            if dash and dash.get("rejected_examples"):
                with st.expander(f"🚫 {dash['rejected_count']} restaurants the AI ruled out"):
                    for r in dash["rejected_examples"]:
                        st.markdown(f"**✗ {r['name']}** --- {', '.join(r['reasons'])}")

            agent_trace = data.get("agent_trace")
            if agent_trace:
                with st.expander("🤖 See how the agents worked through this"):
                    for step in agent_trace:
                        st.markdown(f"- {step}")

    except requests.exceptions.ConnectionError:
        st.error("Could not reach the backend. Make sure `uvicorn main:app --reload` is running.")