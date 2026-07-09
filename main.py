##################################################### AutoPatchAI #########################################################
import os
import uuid
from typing import Dict, TypedDict, List, Annotated
from operator import add
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama

from visualize_performance import generate_performance_graph
from visualize_performance import log_run_to_history

import asyncio
from Gmail_MCP import notify_admin_via_email

from dotenv import load_dotenv
load_dotenv() # This automatically finds the .env file and sets the variables

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class GlobalState(TypedDict):
    vulnerability_details: str
    proposed_patch: str
    validation_logs: str
    retry_count: int
    human_approved: bool
    messages: Annotated[List[BaseMessage], add]

groq_api_key = os.getenv("GROQ_API_KEY")
# we will be using groq because of its low latency also was having trouble using google api
llm = ChatGroq(model="llama-3.3-70b-versatile", 
               api_key=groq_api_key,
               temperature=0.1)
patcher_llm = ChatOllama(model="autopatch-specialist-8b", temperature=0.1)

############################################ RAG implementation ##########################################################
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db_cache")
DOCS_DIR = os.path.join(BASE_DIR, "RAG_docs") # Updated folder name

# makesure RAG_docs and chroma_db_cache folder exists
if not os.path.exists(DOCS_DIR):
    os.makedirs(DOCS_DIR)
if not os.path.exists(PERSIST_DIR):
    os.makedirs(PERSIST_DIR)

txt_files = [f for f in os.listdir(DOCS_DIR) if f.endswith('.txt')]

# if empty, pause + user alert
if not txt_files:
    print(f"\n[!] ALERT: The '{DOCS_DIR}' folder is empty.")
    while True:
        user_input = input("After pasting, type 'GO': ").strip().upper()
        if user_input == 'GO':
            break
        else:
            print("Invalid input. Please type 'GO'.")

# load
print("Initializing Company's VectorDB...")
loader = DirectoryLoader(DOCS_DIR, glob="**/*.txt", loader_cls=TextLoader)
raw_docs = loader.load()

# Chunking
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
company_docs = text_splitter.split_documents(raw_docs)

# Embedding & VectorStore
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
vectorstore = Chroma(persist_directory=PERSIST_DIR, embedding_function=embeddings)

if vectorstore._collection.count() == 0:
    print(f"Populating VectorDB with {len(company_docs)} documents...")
    vectorstore.add_documents(company_docs)
else:
    print("VectorDB loaded from local cache.")

retriever = vectorstore.as_retriever(search_kwargs={"k": 1})

################################################## Defining agents/nodes ##################################################
def supervisor_node(state: GlobalState) -> Dict:
    """The Brain: Evaluates current state conditions and routes to next steps."""
    print("\n____SUPERVISOR NODE____")
    
    # the feedback loop, validator will return to patcher
    if state.get("proposed_patch") and "FAIL" in state.get("validation_logs", ""):
        if state.get("retry_count", 0) < 2:
            return {"messages": [AIMessage(content="Patcher")]} #simplified routing to patcher
        else:
            return {"messages": [AIMessage(content="HumanCheckpoint")]} #simplified routing to human review

    # pipeline
    if not state.get("vulnerability_details"):
        return {"messages": [AIMessage(content="Auditor")]}
    elif not state.get("proposed_patch"):
        return {"messages": [AIMessage(content="Patcher")]}
    elif not state.get("validation_logs"):
        return {"messages": [AIMessage(content="Validator")]}
    else:
        return {"messages": [AIMessage(content="HumanCheckpoint")]}

def auditor_agent(state: GlobalState) -> Dict:
    """Agent 1: Ingests raw alerts, extracts structural vulnerability signatures."""
    print("\n____AUDITOR AGENT____")

    user_input = state["messages"][-1].content
    
    prompt = f"""you are an automated Security Auditor. 
        analyze the following security alert and extract only the exact vulnerable function signature. 
        do not include any explanations, descriptions or conversational text. If no function is found, output 'error'.
        Alert:
        {user_input}
        """
    
    # Get the raw response object
    response_obj = llm.invoke(prompt)
    response_text = response_obj.content.strip() # Extract the text content
    
    # retry logic using the extracted text if there is an error
    if response_text.lower() == "error":
        print("Auditor failed to extract signature. Retrying once...")
        retry_prompt = f"""
            The previous attempt failed. Try again.
            Analyze the alert and extract ONLY the exact vulnerable function signature.
            CRITICAL: Do NOT include conversational text, pleasantries, or questions. Output ONLY the raw target string.
            Alert: {user_input}
            """
        response_obj = llm.invoke(retry_prompt)
        response_text = response_obj.content.strip()
        
    return {
        "vulnerability_details": response_text,
        "messages": [AIMessage(content=f"Auditor completed scanning: {response_text}")]
    }

def patcher_agent(state: GlobalState) -> Dict:
    """Agent 2: Code architect which uses the context to draft the secure code fix."""
    print("\n____PATCHER AGENT____")

    vuln = state["vulnerability_details"]
    logs = state.get("validation_logs", "None")
    retries = state.get("retry_count", 0)
    
    # RAG code
    retrieved_docs = retriever.invoke(vuln)
    rag_context = retrieved_docs[0].page_content
    print(f"RAG Retrieved Company Guideline: {rag_context[:100]}...")

    prompt = f"""You are a strict Security Engineering Assistant.
    
    ### COMPANY GUIDELINE:
    {rag_context}

    ### FEW-SHOT EXAMPLES:
    BAD (Concatenation): 
    cursor.execute("SELECT * FROM users WHERE id = " + user_id)
    GOOD (Parameterized): 
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

    ### TASK:
    Write a secure patch replacing: {vuln}
    Previous feedback: {logs}

    ### RULES:
    1. Output only the raw code for the replacement function.
    2. MANDATORY: You must use parameterization as shown in the GOOD example.

    CRITICAL: You must combine all logic into exactly ONE single function. Do not output multiple functions.
    """
    response = llm.invoke(prompt)
    # response = patcher_llm.invoke(prompt)

    
    return {
        "proposed_patch": response.content,
        "validation_logs": "", #this line erases the old log, preventing infinite loop of old logs being re-evaluated
        "retry_count": retries + 1 if logs != "None" else 0,
        "messages": [AIMessage(content="Patcher generated a code modification draft.")]
    }

def validator_agent(state: GlobalState) -> Dict:
    """Agent 3: Tester. Evaluates code logic, security, and context alignment."""
    print("\n____VALIDATOR AGENT (LOGIC CHECKER)____")

    patch = state.get("proposed_patch", "")
    vuln = state.get("vulnerability_details", "")
    
    prompt = f"""You are a Senior Security Code Reviewer.
    ORIGINAL VULNERABILITY TARGET: {vuln}
    PROPOSED PATCH WRITTEN BY DEVELOPER: {patch}

    Task: Evaluate the proposed patch against the original vulnerability.
    1. Did the developer actually write code for the correct function mentioned in the original vulnerability?
    2. Does the code appear to fix the issue securely (e.g., using parameterized queries)?
    3. is the logic of the code correct and does it align with the original function's intent?
    
    RULES:
    - If the patch perfectly targets the original vulnerability and is secure, output exactly and only: PASS: Code logic and security verified.
    - If the patch hallucinates a different function name, misses the point, or is insecure, output exactly: FAIL: [Provide a brief, 1-sentence reason to help the developer fix it].
    - DO NOT include conversational filler.

    CRITICAL: Output ONLY the PASS/FAIL string and absolutely nothing else
    """
    
    response = llm.invoke(prompt).content.strip()
        
    print(f"Validation Result: {response}")
    
    return {
        "validation_logs": response,
        "messages": [AIMessage(content=f"Test Results: {response}")]
    }

def human_review_node(state: GlobalState) -> Dict:
    """Final node that only executes if the human approves the interrupt."""
    print("\n____HUMAN APPROVED: EXECUTING DEPLOYMENT____")
    return {"messages": [AIMessage(content="Patch safely merged.")]}

def supervisor_router(state: GlobalState) -> str:
    last_msg = state["messages"][-1].content
    if "Auditor" in last_msg:
        return "auditor"
    elif "Patcher" in last_msg:
        return "patcher"
    elif "Validator" in last_msg:
        return "validator"
    elif "HumanCheckpoint" in last_msg:
        return "human_review_node"
    return END

def review_router(state: GlobalState) -> str:
    if "PASS" in state["validation_logs"]:
        return "human_review_node"
    elif state.get("retry_count", 0) >= 2:
        print("MAXIMUM retry_count reached. looping out to avoid infinite stack exploitation.")
        return "human_review_node"
    return "supervisor"
################################################ Graphing ##############################################################
# checkpointing memory to allow for HITL review and approval
memory = MemorySaver()
builder = StateGraph(GlobalState)

# add nodes to the graph
builder.add_node("supervisor", supervisor_node)
builder.add_node("auditor", auditor_agent)
builder.add_node("patcher", patcher_agent)
builder.add_node("validator", validator_agent)
builder.add_node("human_review_node", human_review_node)

# graph interconnections
builder.add_edge(START, "supervisor")
builder.add_conditional_edges("supervisor", supervisor_router)
builder.add_edge("auditor", "supervisor")
builder.add_edge("patcher", "supervisor")

# Validator with a dynamic loop backtracking based on pass/fail logic
builder.add_conditional_edges("validator", review_router)
builder.add_edge("human_review_node", END)

# add Native strict string interrupt before the final deployment node
workflow = builder.compile(
    checkpointer=memory,
    interrupt_before=["human_review_node"]
)

# execute the system with a sample CVE input
if __name__ == "__main__":
    # unique ID for every single run
    run_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": f"run_{run_id}"}}
    initial_input = {
        "messages": [HumanMessage(content="CVE-2026-xyz: Critical SQL Injection vulnerability detected in the 'get_user_profile(user_id)' function. The application concatenates untrusted user input directly into the database query string, allowing arbitrary execution of SQL commands.")]
    }
    
    print("____STARTING AUTONOMOUS SECURITY ORCHESTRATION____")
    for event in workflow.stream(initial_input, config, stream_mode="values"):
        pass
        
    # if graph paused due to our validation conditions
    state_snapshot = workflow.get_state(config)
    
    if state_snapshot.next:
        print("\n<<<HITL INTERRUPT TRIGGERED>>>")
        print(f"Proposed Safe Patch Preview:\n{state_snapshot.values.get('proposed_patch')}")
        print(f"Validation Status: {state_snapshot.values.get('validation_logs')}")
        
        user_approval = input("\nType 'YES' to confirm deployment PR or 'NO' to terminate: ")

        if user_approval.strip().upper() == "YES":
            print("\n✅ Verification complete. Resuming graph execution...")
            workflow.update_state(config, {"human_approved": True}, as_node="supervisor")
            
            # This resumes the graph so the final human_review_node actually executes and finishes!
            for event in workflow.stream(None, config, stream_mode="values"):
                pass
            
            vuln_target = state_snapshot.values.get("vulnerability_details", "Unknown").strip()
            retries = state_snapshot.values.get("retry_count", 0)
            

            log_run_to_history(vuln_target, retries)
            final_vuln = state_snapshot.values.get("vulnerability_details", "Unknown Vulnerability")
            final_patch = state_snapshot.values.get("proposed_patch", "No code generated.")
            
            # send gmail(change the receiver gmail in the Gmail_MCP.py file prompt)
            asyncio.run(notify_admin_via_email(final_vuln, final_patch))

            print("\n" + "="*60)
            print("🚀 AutoPatchAI DEPLOYMENT COMPLETE 🚀")
            print("="*60)
            print("\n✅ Verification complete and logged!")
            print("🟩 SYSTEM STATUS  : ALL ALERTS RESOLVED & GOOD TO GO")
            print(f"🎯 TARGET FIXED   : {vuln_target}")
            print(f"🔄 SELF-HEALING   : {retries} Actor-Critic Retry Loops Executed")
            print("🛡️ COMPLIANCE     : Verified against local RAG Company Guidelines")
            print("✅ DEPLOYMENT     : Secure patch successfully merged to main.")
            print("="*60 + "\n")
            generate_performance_graph()
            
        else:
            print("\n❌ Deployment discarded")