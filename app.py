from dotenv import load_dotenv
import json
import logging
import logging.config
import os
import re
from services import bedrock_agent_runtime
import streamlit as st
import uuid
import yaml

load_dotenv()

# Configure logging using YAML
if os.path.exists("logging.yaml"):
    with open("logging.yaml", "r") as file:
        config = yaml.safe_load(file)
        logging.config.dictConfig(config)
else:
    log_level = logging.getLevelNamesMapping()[(os.environ.get("LOG_LEVEL", "INFO"))]
    logging.basicConfig(level=log_level)

logger = logging.getLogger(__name__)

# Get config from environment variables
agent_id = os.environ.get("BEDROCK_AGENT_ID")
agent_alias_id = os.environ.get("BEDROCK_AGENT_ALIAS_ID", "TSTALIASID")  # TSTALIASID is the default test alias ID
ui_title = os.environ.get("BEDROCK_AGENT_TEST_UI_TITLE", "ANBC Bank, Enterprise Travel Planner")
ui_icon = os.environ.get("BEDROCK_AGENT_TEST_UI_ICON")


def init_session_state():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.citations = []
    st.session_state.trace = {}


# Setting CSS

def apply_custom_css():
    st.markdown(
        """
        <style>
        /* 1. Background and Global Text */
        .stApp {
            background-color: #000000;
            color: #35B8FF;
        }

        /* 2. Typography & Font Sizes */
        html, body, [class*="css"] {
            font-size: 12px;
            line-height: 1.6; /* Readable line height */
        }

        p {
            color: #FFFFFF; /* Primary Blue */
            /*font-size: 2.5rem !important;
            padding-bottom: 0.5rem; */
        }

        li {
            color: darkgray;
        }

        /* 3. Headers (Clear Hierarchies) */
        h1 {
            color: #35B8FF; /* Primary Blue */
            font-size: 2.5rem !important;
            padding-bottom: 0.5rem;
        }
        h2 {
            color: #35B8FF;
            font-size: 2rem !important;
            border-bottom: 1px solid #333333; /* Dark gray contrast */
            padding-bottom: 0.3rem;
        }
        h3 {
            color: #FFFFFF;
            font-size: 1.5rem !important;
            font-weight: 600;
        }

        /* 4. Secondary Elements (Dark Grays for Contrast) */
        [data-testid="stSidebar"] {
            background-color: #121212; /* Dark gray sidebar */
            border-right: 1px solid #333333;
        }
        
        /* Secondary background for widgets/cards */
        .stButton>button, .stTextInput>div>div {
            background-color: #1E1E1E !important;
            color: white !important;
            border: 1px solid #35B8FF !important; /* Blue accent border */
        }

        /* 5. Consistent Spacing */
        .block-container {
            padding-top: 3rem;
            padding-bottom: 3rem;
            gap: 2rem;
        }

        /* Hide the top header bar entirely */
        header[data-testid="stHeader"] {
        display: none !important;
        }

        /* Hide the top header bar entirely */
        header[data-testid="stBottom "] {
        background-color: black !important;
        }

        /* 5. Hide Streamlit Branding & Manage App Button */
        header[data-testid="stHeader"], 
        .stAppDeployButton, 
        #MainMenu, 
        footer {
            display: none !important;
            visibility: hidden;
        }

        /* 6. Make Bottom/Footer Area Black */
        [data-testid="stBottom"] {
            background-color: #000000 !important;
        }
        
        [data-testid="manage-app-button"] {
            background-color: #000000 !important;
        }

        </style>
        """,
        unsafe_allow_html=True
    )

apply_custom_css()

# General page configuration and initialization
st.set_page_config(page_title=ui_title, page_icon=ui_icon, layout="wide")
st.title(ui_title)

st.markdown(
    """
    <div style="
        color: darkgray; 
        font-size: 14px; 
        margin-top: -20px; 
        margin-bottom: 25px; 
        padding-top: 5px;
        opacity: 0.8;
    ">
        Welcome to your ANBC Enterprise Travel Suite. 
        As our strategic hoteling partner, 
        Hilton Hotels & Resorts offers concierge services to all ANBC employees. 
        Your Holiday experience is seamlessly managed and secured through this AI Assistant.
        Currently we are offering stays in Goa, India only.
    </div>
    """, 
    unsafe_allow_html=True
)

if len(st.session_state.items()) == 0:
    init_session_state()

# Sidebar button to reset session state
with st.sidebar:
    if st.button("Reset Session"):
        init_session_state()

# Messages in the conversation
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)

# Chat input that invokes the agent
if prompt := st.chat_input():
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.empty():
            with st.spinner():
                response = bedrock_agent_runtime.invoke_agent(
                    agent_id,
                    agent_alias_id,
                    st.session_state.session_id,
                    prompt
                )
            output_text = response["output_text"]

            # Check if the output is a JSON object with the instruction and result fields
            try:
                # When parsing the JSON, strict mode must be disabled to handle badly escaped newlines
                # TODO: This is still broken in some cases - AWS needs to double sescape the field contents
                output_json = json.loads(output_text, strict=False)
                if "instruction" in output_json and "result" in output_json:
                    output_text = output_json["result"]
            except json.JSONDecodeError as e:
                pass

            # Add citations
            if len(response["citations"]) > 0:
                citation_num = 1
                output_text = re.sub(r"%\[(\d+)\]%", r"<sup>[\1]</sup>", output_text)
                num_citation_chars = 0
                citation_locs = ""
                for citation in response["citations"]:
                    for retrieved_ref in citation["retrievedReferences"]:
                        citation_marker = f"[{citation_num}]"
                        citation_locs += f"\n<br>{citation_marker} {retrieved_ref['location']['s3Location']['uri']}"
                        citation_num += 1
                output_text += f"\n{citation_locs}"

            st.session_state.messages.append({"role": "assistant", "content": output_text})
            st.session_state.citations = response["citations"]
            st.session_state.trace = response["trace"]
            st.markdown(output_text, unsafe_allow_html=True)

trace_types_map = {
    "Pre-Processing": ["preGuardrailTrace", "preProcessingTrace"],
    "Orchestration": ["orchestrationTrace"],
    "Post-Processing": ["postProcessingTrace", "postGuardrailTrace"]
}

trace_info_types_map = {
    "preProcessingTrace": ["modelInvocationInput", "modelInvocationOutput"],
    "orchestrationTrace": ["invocationInput", "modelInvocationInput", "modelInvocationOutput", "observation", "rationale"],
    "postProcessingTrace": ["modelInvocationInput", "modelInvocationOutput", "observation"]
}

# Sidebar section for trace
with st.sidebar:
    st.title("Trace")

    # Show each trace type in separate sections
    step_num = 1
    for trace_type_header in trace_types_map:
        st.subheader(trace_type_header)

        # Organize traces by step similar to how it is shown in the Bedrock console
        has_trace = False
        for trace_type in trace_types_map[trace_type_header]:
            if trace_type in st.session_state.trace:
                has_trace = True
                trace_steps = {}

                for trace in st.session_state.trace[trace_type]:
                    # Each trace type and step may have different information for the end-to-end flow
                    if trace_type in trace_info_types_map:
                        trace_info_types = trace_info_types_map[trace_type]
                        for trace_info_type in trace_info_types:
                            if trace_info_type in trace:
                                trace_id = trace[trace_info_type]["traceId"]
                                if trace_id not in trace_steps:
                                    trace_steps[trace_id] = [trace]
                                else:
                                    trace_steps[trace_id].append(trace)
                                break
                    else:
                        trace_id = trace["traceId"]
                        trace_steps[trace_id] = [
                            {
                                trace_type: trace
                            }
                        ]

                # Show trace steps in JSON similar to the Bedrock console
                for trace_id in trace_steps.keys():
                    with st.expander(f"Trace Step {str(step_num)}", expanded=False):
                        for trace in trace_steps[trace_id]:
                            trace_str = json.dumps(trace, indent=2)
                            st.code(trace_str, language="json", line_numbers=True, wrap_lines=True)
                    step_num += 1
        if not has_trace:
            st.text("None")

    st.subheader("Citations")
    if len(st.session_state.citations) > 0:
        citation_num = 1
        for citation in st.session_state.citations:
            for retrieved_ref_num, retrieved_ref in enumerate(citation["retrievedReferences"]):
                with st.expander(f"Citation [{str(citation_num)}]", expanded=False):
                    citation_str = json.dumps(
                        {
                            "generatedResponsePart": citation["generatedResponsePart"],
                            "retrievedReference": citation["retrievedReferences"][retrieved_ref_num]
                        },
                        indent=2
                    )
                    st.code(citation_str, language="json", line_numbers=True, wrap_lines=True)
                citation_num = citation_num + 1
    else:
        st.text("None")
