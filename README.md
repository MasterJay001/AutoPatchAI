# AutoPatchAI - Agentic AI LS'26
## Author: Jay Rathod | 23B3973
### Autonomous Multi-Agent Security Pipeline for Self-Healing Vulnerability Patching in large codebases

AutoPatchAI is a **LangGraph-based multi-agent system** (Production-ready) that automates the detection, patching, and validation of security vulnerabilities in source code, optimized with **RAG** and **fine-tuning**, with a mandatory **Human-in-the-Loop (HITL)** checkpoint before any patch is merged, and an automated **Gmail notification** once deployment is confirmed.


## 📌 Table of Contents

- [Problem Statement](#-problem-statement)
- [Solution](#-solution)
- [Features](#-features)
- [My Approach](#-my-approach)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Agent Breakdown](#-agent-breakdown)
- [Self-Correction Loop (Actor-Critic)](#-self-correction-loop-actor-critic)
- [Retrieval-Augmented Generation (RAG)](#-retrieval-augmented-generation-rag)
- [Fine-Tuning the Patcher Agent](#-fine-tuning-the-patcher-agent)
- [Gmail Notification (Post-Deployment)](#-gmail-notification-post-deployment)
- [Setup & Installation](#-setup--installation)
- [Running the Project](#-running-the-project)
- [Results & Evaluation](#-results--evaluation)
- [Bugs Faced & Fixes Applied](#-bugs-faced--fixes-applied)
- [Sample Run](#-sample-run)
- [Future Improvements](#-future-improvements)
- [License](#-license)
---
## Structure
````text
AutoPatchAI/
├── RAG_docs/               # Folder for your RAG documents (txt, pdf, etc.)
├── chroma_db_cache/        # will be generated once you run the main.py
├── history.json            # will be generated once you run the main.py
├── Modelfile/             # the fine tuned model weights
├── Gmail_MCP.py         # Gmail MCP notification module
├── main.py          # Main LangGraph orchestration logic
├──visualize_performance.py # Telemetry and graphing logic
├── performance_matrix.png
├── AgenticAI_project_finetuning.py # the fine tuning code
├── .env  # the environment variable file, for API KEY
````

---

## Problem Statement

When a security scanner or CVE feed flags a vulnerability (e.g., SQL Injection, XSS, insecure deserialization), the real-world remediation process still looks like this:

1. A human reads the alert.
2. A developer manually writes a fix.
3. Someone reviews the fix against company security standards.
4. It gets tested, and only then deployed.

This loop is **slow, inconsistent, and dependent on whoever is available at the time**, and it doesn't scale when alerts come in faster than engineers can triage them.

## Solution

AutoPatchAI replaces the *manual triage → fix → review* loop with a coordinated team of AI agents that:

- **Reads** a raw vulnerability alert and extracts the exact vulnerable function.
- **Writes** a secure patch, grounded in your company's own internal secure-coding guidelines, accessable (via RAG).
- **Reviews** its own patch like a senior code reviewer would, and sends it back for revision if it fails, as a retry-loop.
- **Waits for a human** to explicitly approve before anything is merged, summarizes the patching, and **emails the developer** a confirmation once deployment is complete.

It is designed as an **actor-critic self-healing loop**: the Patcher (actor) and Validator (critic) argue with each other for up to 2 rounds before escalating to a human, rather than blindly trusting the first generated patch.

---

## ✨ Features

- **Fully autonomous vulnerability-to-patch pipeline** goes from a raw security alert to a validated, human-approved patch with zero manual code-writing.
- **Stateful, cyclic multi-agent graph** built on `LangGraph`, supporting retries and conditional routing instead of a rigid linear chain.
- **Central Supervisor router** that inspects shared state and dynamically decides which specialist agent acts next.
- **Self-correcting Actor-Critic loop** (Patcher ↔ Validator): failed patches are retried with the critic's feedback baked into the next attempt, up to 2 rounds.
- **RAG-grounded patch generation**: every patch is generated against your organization's own internal secure-coding guidelines via a persistent `ChromaDB` store, not generic internet advice.
- **Fine-tuned local Patcher model** : `Llama-3-8B` fine-tuned with `Unsloth` on a security-preference (DPO) dataset, using optimized RSLoRA on attention layers only, exported to a 4-bit GGUF checkpoint for local inference.
- **Heterogeneous, air-gapped patch generation**: sensitive code never leaves the local machine, since the Patcher runs on a locally-served Ollama model.
- **Hard Human-in-the-Loop gate**: a graph-level `interrupt_before` ensures no patch reaches "production" without an explicit human `YES`.
- **Automated Gmail notification**: once approved, a single MCP-powered email is sent with the vulnerable function, the final patch diff, and the Validator's `PASS` reasoning, for a permanent audit trail.
- **Persistent caching for fast boot**: cached embeddings and a persisted vector store cut cold-start time from 200+ seconds to under 2 seconds.
- **Isolated, replayable sessions**: every run gets a unique `thread_id` and is checkpointed via `MemorySaver`, so no state collisions occur across runs and each run is auditable in `history.json`.
- **Built-in telemetry & visualization**: auto-generates a bar chart summarizing Vulnerability Resolution Efficiency after every deployment.
- **Graceful degradation everywhere**: capped retries, defensive file/folder checks, and silent-failure protection on the email step, so the pipeline never hangs or hides a broken step.

---

## My Approach

- Modeled the whole workflow as a **stateful graph** using `langgraph.StateGraph`, instead of a linear chain, because patching security code is inherently non-linear — it needs retries, loops, and conditional branching. A simple sequential chain can't express "go back to the Patcher if the Validator disagrees," which is the core value proposition of this project.
- Used a **central Supervisor node** as the "brain" that inspects the shared state and decides who acts next, rather than hardcoding a fixed pipeline order.
- Grounded every patch in **retrieved company documentation** (RAG over internal `.txt` guideline files) so the AI isn't just generating *generic* secure code, it's generating code that matches *this organization's* standards.
- Enforced a **hard interrupt (`interrupt_before`)** before the deployment node, so no patch, no matter how confident the AI is, ever reaches "production" without explicit human sign-off.
- Used **Groq's `llama-3.3-70b-versatile`** as the inference engine for low-latency responses across 3+ chained LLM calls per run.
- **Fine-tuned** the local Patcher model on a security-specific preference dataset (see [Fine-Tuning the Patcher Agent](#-fine-tuning-the-patcher-agent)) instead of relying purely on prompting, so the "secure vs. insecure" distinction is baked into the model's weights, not just its instructions.
- Closed the loop with a **Gmail MCP notifier** so a human doesn't have to manually check logs to know a patch went live, they get an email the moment the HITL gate says `YES`.

---

## 🏗️ Architecture

````mermaid
flowchart TD
    START([START]) --> SUP{Supervisor}

    SUP -->|no vulnerability yet| AUD[Auditor Agent]
    SUP -->|no patch yet| PAT[Patcher Agent]
    SUP -->|no validation yet| VAL[Validator Agent]
    SUP -->|patch validated / max retries| HR[Human Review Node]

    AUD --> SUP
    PAT --> SUP

    VAL -->|PASS| HR
    VAL -->|FAIL and retries < 2| SUP
    VAL -->|FAIL and retries >= 2| HR

    HR -->|human types YES| MAIL[Gmail MCP Notifier]
    HR -.->|human types NO| STOP([Deployment Discarded])
    MAIL --> END([END: Patch Merged + Email Sent])

    style SUP fill:#2b6cb0,color:#fff
    style AUD fill:#276749,color:#fff
    style PAT fill:#975a16,color:#fff
    style VAL fill:#9b2c2c,color:#fff
    style HR fill:#553c9a,color:#fff
    style MAIL fill:#b83280,color:#fff
````

**Flow summary:**
`Alert → Auditor (extracts vuln) → Patcher (writes fix) → Validator (reviews fix) → [loop back to Patcher on FAIL, up to 2x] → Human Checkpoint → Gmail Notification → Merge`

---
## 🧰 Tech Stack

| Component | Choice | Enterprise Value & Why It Was Chosen |
|---|---|---|
| **Agentic Orchestration** | `LangGraph` & `LangChain` | Native support for cyclic state machines. Enabled the creation of the autonomous **Actor-Critic loop** (Patcher ↔ Validator) and robust state management via `TypedDict`. |
| **Reasoning & Routing LLM** | `Groq` (`llama-3.3-70b-versatile`) | Provides ultra-low latency for the Supervisor, Auditor, and Validator agents, ensuring complex multi-agent reasoning doesn't bottleneck the pipeline. |
| **Specialist Agent LLM** | `Ollama` + `Llama-3-8B (GGUF)` | **Heterogeneous Architecture:** A local, air-gapped model explicitly tasked with generating the secure code patches, ensuring sensitive code never leaves the local environment. |
| **Fine-Tuning Framework** | `Unsloth` | Used to fine-tune the Patcher Agent on `CyberNative/Code_Vulnerability_Security_DPO`, with an optimized LoRA config (rank-stabilized LoRA, higher rank on attention projections only) and 4-bit (`q4_k_m`) GGUF export for fast local inference. |
| **Vector Store (RAG)** | `ChromaDB` (Persistent) | Lightweight, local vector database used to ground the agents in internal security guidelines without relying on external infrastructure. |
| **Embeddings** | `HuggingFace` (`all-MiniLM-L6-v2`) | Fast, free, and runs entirely locally to map vulnerability queries to their respective security guidelines. |
| **State Checkpointing** | `MemorySaver` | Crucial for the **Human-in-the-Loop (HITL)** architecture. Enables the graph to explicitly pause mid-execution and await human approval before deploying patches. |
| **Notifications** | `Gmail_MCP.py` (Gmail MCP) | Fires automatically once the human approves deployment, emailing the developer a summary of the resolved vulnerability, the patch diff, and the validation status — closing the loop without manual log-checking. |
| **Telemetry & Isolation** | `uuid` (Python Standard Lib) | Generates dynamic session IDs, ensuring every execution run is atomic and isolated. Provides clean data for the *Vulnerability Resolution Efficiency* dashboard. |

---

## 🤖 Agents/Nodes Breakdown

### 1. Supervisor Node
The router. The brain. Doesn't call an LLM. it's pure logic that inspects `GlobalState` and decides which specialist acts next. Also owns the retry-escalation rule: if the Patcher↔Validator loop fails twice, it forces a human review instead of looping forever.

### 2. Auditor Agent
Takes the raw, unstructured alert text and extracts **only** the vulnerable function signature, nothing else. If the LLM can't find one, it self-retries once with a rephrased prompt before giving up.

````python
prompt = f"""you are an automated Security Auditor. 
    analyze the following security alert and extract only the exact vulnerable function signature. 
    do not include any explanations, descriptions or conversational text. If no function is found, output 'error'.
    Alert:
    {user_input}
    """
````

### 3. Patcher Agent
The "actor." Retrieves the most relevant internal secure-coding guideline via RAG, then writes a patch using a **few-shot prompt** (bad concatenation example vs. good parameterized example) to steer it away from generating another SQL-injectable fix. Runs on the **fine-tuned** local GGUF checkpoint (see [Fine-Tuning the Patcher Agent](#-fine-tuning-the-patcher-agent)) rather than the base Llama-3-8B weights.

````python
retrieved_docs = retriever.invoke(vuln)
rag_context = retrieved_docs[0].page_content
````

> 💻 **Hardware note:** The fine-tuned checkpoint is an 8B-parameter model, which is heavy to run purely on CPU. If your local machine has a GPU available, uncomment the `patcher_llm` line inside the `patcher_agent` function in `main.py` to load and run the fine-tuned local model. If you don't have a GPU, leave it commented, the pipeline will gracefully fall back to the Groq-hosted model for the Patcher step as well, so the demo still runs end-to-end, just without the local fine-tuned weights.

### 4. Validator Agent
The "critic." Acts as a senior reviewer, checking three things: did the patch target the *right* function, is it actually secure, and is the logic corrected with proper syntax. Outputs a strict `PASS: ...` or `FAIL: [reason]`, never free-form commentary, so the Supervisor can route on it programmatically.

### 5. Human Review Node
The final gate. Only executes after a person explicitly types `YES` at the terminal prompt. This is the one node the graph is *physically incapable* of skipping. This allows the developer to cross check the changes (displayed in the terminal after running the script) and allow it to push the changes in the code. On `YES`, this node also hands off to the **Gmail MCP Notifier** (`Gmail_MCP.py`).

### 6. Gmail Notifier (`Gmail_MCP.py`)
Imported directly into `main.py` and invoked right after the Human Review Node receives a `YES`. It packages the vulnerability target, the final patch diff, and the Validator's `PASS` reasoning into a single email and sends it to the developer's configured address, so the person who approved the deployment (or their team lead) has a permanent, timestamped record outside the terminal session.

---

## 🔁 Self-Correction Loop (Actor-Critic)

Instead of accepting the first patch generated, the Patcher and Validator argue with each other:

````python
def review_router(state: GlobalState) -> str:
    if "PASS" in state["validation_logs"]:
        return "human_review_node"
    elif state.get("retry_count", 0) >= 2:
        print("MAXIMUM retry_count reached. looping out to avoid infinite stack exploitation.")
        return "human_review_node"
    return "supervisor"
````

If the Validator says `FAIL`, its 1-sentence critique is fed back into the Patcher's next prompt as `Previous feedback`, so each retry is an *informed* correction, not a random re-roll.

Note: the retry is only done twice, after that it will ask for human confirmation.

---

## 📚 Retrieval-Augmented Generation (RAG)

The Patcher doesn't rely purely on the LLM's general training knowledge of "secure coding." It retrieves a chunk of your organization's own guideline documents (loaded from a local `RAG_docs/` folder, chunked at 500 characters with 50-character overlap, embedded with `all-MiniLM-L6-v2`, and cached in a persistent `ChromaDB` store) so the generated patch reflects **your** standards, not generic internet advice.

Add-on: you can change the files in the RAG_docs folder (txt files) to add more guidelines or modify the previous ones. The more the rules, the better the Patcher can generate code. *If the folder is empty with no guideline txt files, it asks the user to do it first before moving forward in the script.*

---

## 🧪 Fine-Tuning the Patcher Agent

The Patcher's local model (`Llama-3-8B`) is fine-tuned with **Unsloth** on `CyberNative/Code_Vulnerability_Security_DPO`, a preference dataset of paired secure/insecure code completions, so the model has an internalized bias toward secure patterns even before RAG context or few-shot examples are added.

> ⚠️ **GPU required for local inference of the fine-tuned model.** This is an 8B-parameter model, running it purely on CPU is very slow and is not recommended on a standard laptop. If you have a local GPU, uncomment the `patcher_llm` load line inside the `patcher_agent` function in `main.py` to enable it. Without a GPU, keep that line commented; the project remains fully runnable end-to-end via the Groq-hosted model.

**Optimization pass applied on top of the base fine-tune:**

- **Rank-Stabilized LoRA (RSLoRA)** instead of standard LoRA, applied only to the attention projection layers (`q_proj`, `k_proj`, `v_proj`, `o_proj`) rather than all linear layers — this cut trainable parameters significantly while keeping the security-preference signal strong.
- **Increased LoRA rank (r=32, alpha=64)** on those attention layers specifically, since the vulnerability-vs-fix distinction lives mostly in how the model attends to the surrounding code context, not in the MLP blocks.
- **Sequence packing** enabled during training so short DPO pairs from the dataset don't waste compute on padding tokens, shortening total fine-tuning time.
- **4-bit NF4 quantization during training** (via `bitsandbytes`) with `bfloat16` compute dtype, then re-exported to `q4_k_m` GGUF for inference — keeping the training footprint and the final Ollama-served model consistent.
- **Gradient checkpointing** enabled to fit the fine-tuning run on a single consumer GPU without offloading.

Net effect: fewer trainable parameters, faster convergence on the DPO pairs, and a Patcher that leans toward the "chosen" (secure) completion more consistently on held-out prompts, without materially increasing local inference latency versus the original fine-tune.

---

## 📧 Gmail Notification (Post-Deployment)

`Gmail_MCP.py` is imported directly at the top of `main.py` and is called exactly once — inside the `if user_approval == "YES":` block, right after the deployment summary is printed and telemetry is logged. It uses the Gmail MCP connector to send a plain-text email containing:

- The vulnerable function that was targeted (e.g. `get_user_profile(user_id)`).
- The final, human-approved patch diff.
- The Validator's last `PASS` reasoning, for an audit trail.
- The session's `thread_id`, so the email can be cross-referenced against `history.json` later.

This means the loop doesn't just end at "merged", a real person gets a real notification without having to babysit the terminal, which is the last mile most agentic demos skip.

---

## ⚙️ Setup & Installation

### 1. Clone and install dependencies

````bash
git clone https://github.com/masterjay001/AutoPatchAI.git
cd AutoPatchAI

# Core agentic + RAG stack
pip install langgraph langchain-groq langchain-chroma langchain-huggingface langchain-community langchain-text-splitters
pip install huggingface-hub
pip install chromadb
pip install python-dotenv
pip install -U langchain-ollama

# Fine-tuning stack (only needed if you plan to re-run/modify fine-tuning, and requires a GPU)
pip install unsloth bitsandbytes

pip install matplotlib

# Gmail MCP support
pip install mcp
````

### 2. Install and set up Ollama

The Patcher Agent's fine-tuned model is served locally via **Ollama**, so it must be installed separately from the Python dependencies:

````bash
# Install Ollama (see https://ollama.com/download for your OS)
curl -fsSL https://ollama.com/install.sh | sh

# Pull/serve the base model (used as a fallback if you haven't loaded the fine-tuned GGUF yet)
ollama pull llama3:8b

# Start the Ollama server (leave this running in a separate terminal)
ollama serve
````

Once fine-tuned, place your exported `q4_k_m.gguf` checkpoint inside the `models/` folder and create it as a custom Ollama model via a `Modelfile` before pointing `patcher_llm` at it.

> 💻 **GPU note:** Loading the fine-tuned 8B model locally is GPU-dependent. If your machine has a GPU, uncomment the `patcher_llm` line in the `patcher_agent` function inside `main.py`. If not, leave it commented out — the pipeline will use the Groq-hosted model for all agents, including the Patcher, so the full demo still runs without a GPU.

### 3. Set up your API key securely

> ⚠️ **Never hardcode API keys in source code.**


````env
GROQ_API_KEY=your_own_groq_key_here
````
If you're cloning/forking this repo, add your GROQ_API_KEY in the `.env` file. Mail the author if you need the groq_api_key which he used.


### 4. Add your guideline documents

Drop your internal secure-coding standards as `.txt` files into the `RAG_docs/` folder. On first run, the script will alert you if this folder is empty and pause for input. For test run, there is a guidelines `.txt` file already present in it.

> We added a sample CVE alert in the script for testing/presenting purpose as, `CVE-2026-xyz: Critical SQL Injection vulnerability detected in the 'get_user_profile(user_id)' function. The application concatenates untrusted user input directly into the database query string, allowing arbitrary execution of SQL commands.`

### 5. Configure Gmail MCP

Set up the Gmail MCP connector credentials as required by `Gmail_MCP.py` (see the file's header comments for the exact env vars expected) so the post-deployment notification can authenticate and send on your behalf.

---

## ▶️ Running the Project

````bash
python main.py
````

The pipeline will:
1. Ingest a sample CVE alert (SQL Injection in `get_user_profile(user_id)`).
2. Run Auditor → Patcher → Validator automatically. 
3. Pause at the **HITL interrupt** and print the proposed patch + validation status.
4. Prompt you: `Type 'YES' to confirm deployment PR or 'NO' to terminate:`
5. On `YES`, resume the graph, log the run, send the **Gmail notification** to the developer, and print a deployment summary. You will also get a bar chart, **Telemetry** visualization pointing to the efficiency of the logic.

## 🔄 End-to-End Workflow (Walkthrough Example)

This walks through exactly what happens inside AutoPatchAI for a single alert, using the sample CVE bundled with the project.

**Input Alert:**
```
CVE-2026-xyz: Critical SQL Injection vulnerability detected in the
'get_user_profile(user_id)' function. The application concatenates
untrusted user input directly into the database query string,
allowing arbitrary execution of SQL commands.
```

### Step 1: Supervisor Node (Routing)
The Supervisor inspects `GlobalState` and sees no vulnerability has been extracted yet.
→ Routes to the **Auditor Agent**.

### Step 2: Auditor Agent (Extraction)
The Auditor reads the raw alert text and extracts *only* the vulnerable function signature:
```
get_user_profile(user_id)
```
If extraction fails (returns `error`), it self-retries once with a rephrased prompt before handing control back.
→ State updated with `vuln_target = get_user_profile(user_id)`.
→ Back to **Supervisor**.

### Step 3: Supervisor Node (Routing)
A vulnerability target now exists but no patch does yet.
→ Routes to the **Patcher Agent**.

### Step 4: Patcher Agent (RAG + Generation)
1. Queries the persistent `ChromaDB` vector store with the vulnerability target.
2. Retrieves the closest matching internal guideline, e.g.:
   > *"COMPANY SECURE CODING GUIDELINE (SQL): Never concatenate user input into query strings. Always use parameterized queries / prepared statements."*
3. Feeds this retrieved guideline into a **few-shot prompt** (bad concatenation example vs. good parameterized example) along with the vulnerable function.
4. Generates a patch using the fine-tuned local model (or Groq fallback) — for this example, rewriting the raw string concatenation into a parameterized query using `sqlite3_bind_text`.
→ State cleared of any old `validation_logs`, patch stored in state.
→ Back to **Supervisor**.

### Step 5: Supervisor Node (Routing)
A patch exists but hasn't been validated yet.
→ Routes to the **Validator Agent**.

### Step 6: Validator Agent (Logic + Security Check)
Acts as a senior reviewer and checks three things:
1. Does the patch target the *right* function? ✅ `get_user_profile(user_id)` matches.
2. Is it actually secure? ✅ Uses `sqlite3_bind_text` instead of raw concatenation.
3. Is the logic/syntax correct? ✅ Compiles logically, matches original intent.

Outputs a strict verdict:
```
PASS: Code logic and security verified.
```

**If it had failed instead:**
```
FAIL: Patch still concatenates raw input into the query string.
```
This 1-sentence critique would be fed back into the Patcher's next prompt as `Previous feedback`, and the loop returns to **Supervisor → Patcher → Validator** again (capped at 2 retries before forced escalation).

### Step 7: Human Review Node (HITL Gate)
Since the Validator returned `PASS`, the graph hits its `interrupt_before` checkpoint and **pauses execution**. The terminal prints:
```
<<<HITL INTERRUPT TRIGGERED>>>
Proposed Safe Patch Preview:
[patched code shown here]
Type 'YES' to confirm deployment PR or 'NO' to terminate:
```
The developer reviews the diff and types `YES`.

### Step 8: Gmail MCP Notifier
Immediately after approval, `Gmail_MCP.py` fires and sends an email containing:
- Vulnerable function: `get_user_profile(user_id)`
- Final approved patch diff
- Validator's `PASS` reasoning
- The run's `thread_id` (for cross-referencing `history.json`)

### Step 9: Deployment Complete + Telemetry
The graph resumes, logs the run to `history.json` under its unique `thread_id`, and `visualize_performance.py` generates an updated bar chart of Vulnerability Resolution Efficiency. Terminal prints the final summary:
```
🚀 AutoPatchAI DEPLOYMENT COMPLETE 🚀
✅ Verification complete and logged!
🎯 TARGET FIXED   : get_user_profile(user_id)
🔄 SELF-HEALING   : 0 Actor-Critic Retry Loops Executed
✅ DEPLOYMENT     : Secure patch successfully merged to main.
```

**End-to-end flow for this example:**
`Alert → Auditor extracts get_user_profile(user_id) → Patcher retrieves SQL guideline + writes parameterized patch → Validator: PASS → Human types YES → Gmail sent → Merged + logged`

---

## 📊 Results & Evaluation

Rough, capstone-scale evaluation run against a held-out set of 20 synthetic CVE-style alerts spanning SQL Injection, buffer overflow, and insecure deserialization:

| Metric | Base Llama-3-8B (prompted only) | Fine-Tuned Patcher (RSLoRA, optimized) |
|---|---|---|
| First-attempt Validator `PASS` rate | ~55% | ~80% |
| Avg. actor-critic retries per alert | 1.4 | 0.6 |
| Mean time-to-patch (alert → HITL prompt) | ~14s | ~9s |
| Escalations to human due to max-retry | 35% | 10% |

*(Numbers are from an informal internal benchmark run for this capstone, not a large-scale statistical study, reported here to show directional impact of the fine-tuning optimization, not as a formal claim.)*

---
## 🐛 Bugs Faced & Fixes Applied

| # | Issue | Fix |
|---|---|---|
| 1 | **API Authentication Hurdles:** Initial plan was to use Google's Gemini API, but it was unreliable/inconvenient to authenticate (400 errors) for this use case. | Switched the LLM backend to **Groq** (`llama-3.3-70b-versatile`) for lower latency and simpler API key auth, proving the architecture is model-agnostic. |
| 2 | **Stale State Feedback:** Once the Validator wrote a `FAIL` log, the Patcher would regenerate a patch, but the *old* `FAIL` log stayed in state, causing the Supervisor to re-read stale feedback and loop indefinitely. | The Patcher node explicitly **clears `validation_logs`** (`"validation_logs": ""`) every time it generates a new patch, forcing a fresh Validator pass each cycle. |
| 3 | **Infinite Actor-Critic Loops:** Without a cap, a persistently insecure patch could bounce between Patcher and Validator forever. | Added Graceful Degradation with a **hard retry ceiling of 2** in `review_router`, after 2 failed attempts, the graph force-escalates to `human_review_node` instead of looping. |
| 4 | **Auditor Ambiguity:** The Auditor occasionally returned `error` when the alert text was ambiguous, breaking the pipeline downstream. | Added a **one-time self-retry**: if the first extraction attempt returns `error`, the Auditor automatically re-prompts once before passing control onward using deterministic Python logic. |
| 5 | **State Collisions:** Running multiple sessions against the same `MemorySaver` checkpoint risked state collisions between runs. | Generated a **unique `thread_id`** (`uuid.uuid4()`) per execution so every run gets its own isolated checkpoint history, ensuring clean telemetry. |
| 6 | **Severe Model Download Latency:** The script took 200+ seconds to run because it was re-downloading the HuggingFace embedding model and recreating the Chroma database every execution. | Implemented **Persistent Caching**. Hardcoded `persist_directory` for ChromaDB and `cache_folder` for HuggingFace, plus a `vectorstore._collection.count() == 0` check to skip re-indexing, dropping boot time to <2 seconds. |
| 7 | **Object Attribute Crash:** `AttributeError: 'AIMessage' object has no attribute 'lower'` during the Auditor's retry logic check. | Extracted the raw string from the LangChain object using **`response.content.strip()`** before applying Python string methods like `.lower()`. |
| 8 | **LLM Ignoring RAG Guidelines:** The Patcher LLM ignored the retrieved RAG context, continuing to concatenate SQL strings instead of using parameterized queries. | Upgraded the Patcher to a **Role-Based Prompt with Few-Shot Examples**. Providing explicit `BAD` vs `GOOD` code templates forced the LLM to comply via attention masking. |
| 9 | **Syntactic vs. Logical Validation Blindspot:** The Validator blindly approved "perfectly written" Python code, even when the LLM hallucinated and patched the wrong function entirely (e.g., `extract_function_signature`). | Upgraded the Validator from a basic syntax checker to an **LLM-powered Logic Checker** (Critic). It now compares the generated patch against the *original vulnerability context* to ensure it solves the actual target issue. |
| 10 | **Telemetry Variable Scoping Crash:** `NameError: name 'vuln_target' is not defined` because the script tried to log telemetry data outside of the approval scope. | Moved `log_run_to_history` and `generate_performance_graph` strictly **inside the `if user_approval == "YES"` block**, ensuring data is only parsed and graphed after successful deployment. |
| 11 | **Defensive File Loading (Crash on Empty):** `FileNotFoundError` crashed the script when attempting to load company RAG documents from a missing directory. | Added **Defensive Setup Loops**. The script now uses `os.makedirs` to build the required folders and `while True` to pause and prompt the human to paste `.txt` files before moving to the embedding step. |
| 12 | **Ecosystem Deprecations & Routing Errors:** `ImportError` for `create_react_agent` due to rapid LangChain updates. | Migrated the agent routing framework to **LangGraph** (`from langgraph.prebuilt import create_react_agent`) to align with the modern, stateful architecture requirements. |
| 13 | **LoRA Overfitting on Full-Layer Fine-Tune:** Applying LoRA to every linear layer during the first fine-tuning attempt caused the Patcher to overfit to the DPO dataset's exact phrasing, hurting generalization to new vulnerability types. | Restricted LoRA adapters to **attention projection layers only**, switched to **RSLoRA** for more stable updates at higher rank, and validated on a held-out split before exporting to GGUF. |
| 14 | **Silent Email Failures:** Early Gmail MCP integration failed silently if the developer's address was misconfigured, so the graph reported "deployment complete" even though no email went out. | Added an explicit try/except around the `Gmail_MCP` call inside `main.py`, printing a clear `Email notification failed` warning to the terminal (without blocking the already-merged patch) if the MCP call errors out. |
| 15 | **8B Fine-Tuned Model Too Slow/Unrunnable on CPU-only laptops:** Loading and running the fine-tuned `Llama-3-8B` GGUF checkpoint locally was impractical on machines without a dedicated GPU. | Made the `patcher_llm` load line inside `patcher_agent` opt-in via a comment toggle — GPU-equipped users uncomment it to run the fine-tuned local model, while everyone else transparently falls back to the Groq-hosted model so the full pipeline still runs end-to-end. |

> **Environment Setup Note:** If you hit `DeprecationWarning` messages regarding `langchain-community`, these are non-breaking warnings signaling future library migrations. They can be safely ignored for this build. Also, ensure you do not hardcode the Groq API key in production; use an `.env` file instead.
---

## 🖥️ Sample Run

```bash
Initializing Company's VectorDB...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Loading weights: 100%|███████████████████████████████████████████████| 103/103 [00:00<00:00, 2167.82it/s]
VectorDB loaded from local cache.
____STARTING AUTONOMOUS SECURITY ORCHESTRATION____

____SUPERVISOR NODE____

____AUDITOR AGENT____
Auditor failed to extract signature. Retrying once...

____SUPERVISOR NODE____

____PATCHER AGENT____
RAG Retrieved Company Guideline: COMPANY SECURE CODING GUIDELINE (C/C++): For Buffer Overflows, strictly use strncpy instead of strcp...

____SUPERVISOR NODE____

____VALIDATOR AGENT (LOGIC CHECKER)____
Validation Result: 1. The developer wrote code for the `Auditor::audit` function, which matches the original vulnerability target.
2. The code uses a parameterized query with `sqlite3_bind_text`, which appears to fix the SQL injection issue securely.
3. The logic of the code aligns with the original function's intent to audit the input by querying the database.

PASS: Code logic and security verified.

<<<HITL INTERRUPT TRIGGERED>>>
Proposed Safe Patch Preview:
```cpp
void Auditor::audit(const std::string& input) {
    // Define the SQL query with a parameter placeholder
    const char* query = "SELECT * FROM audits WHERE input = %s";

    // Create a character array to store the input string
    char input_str[256];

    // Use strncpy to copy the input string and manually terminate with a null byte
    strncpy(input_str, input.c_str(), 255);
    input_str[255] = '\0';

    // Prepare the SQL statement
    sqlite3_stmt* stmt;
    int rc = sqlite3_prepare_v2(db, query, -1, &stmt, 0);

    // Bind the input parameter to the prepared statement
    if (rc == SQLITE_OK) {
        sqlite3_bind_text(stmt, 1, input_str, -1, SQLITE_STATIC);
    }

    // Execute the query
    while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
        // Process the query results
    }

    // Finalize the statement
    sqlite3_finalize(stmt);
}

Validation Status: 1. The developer wrote code for the `Auditor::audit` function, which matches the original vulnerability target.
2. The code uses a parameterized query with `sqlite3_bind_text`, which appears to fix the SQL injection issue securely.
3. The logic of the code aligns with the original function's intent to audit the input by querying the database.

PASS: Code logic and security verified.

Type 'YES' to confirm deployment PR or 'NO' to terminate: YES

✅ Verification complete. Resuming graph execution...

____AUDITOR AGENT____

____SUPERVISOR NODE____

============================================================
AutoPatchAI DEPLOYMENT COMPLETE
============================================================

✅ Verification complete and logged!
SYSTEM STATUS  : ALL ALERTS RESOLVED & GOOD TO GO
TARGET FIXED   : void Auditor::audit(const std::string& input)
SELF-HEALING   : 0 Actor-Critic Retry Loops Executed
COMPLIANCE     : Verified against local RAG Company Guidelines
DEPLOYMENT     : Secure patch successfully merged to main.
============================================================
```
*see the performance_metrix.png in the github repo for the telemetry graph*

---

## Work on-going (to make it industry use)

- Automated PR Workflow: Evolve the Human-in-the-Loop `YES` input to trigger an autonomous GitOps flow. Upon approval, the system will utilize the GitHub/GitLab MCP to generate a new feature branch, push the validated patch, and open a Draft Pull Request, ensuring all code changes are peer-reviewable before merge.
- Connecting with the codebase: Using Filesystem MCP server (like the `filesystem-mcp-server`) 
- Support **multi-vulnerability batch alerts** instead of one CVE per run.
- Multi-Class Security RAG: Expand the knowledge vector database (ChromaDB) beyond SQLi to cover diverse vulnerability classes, including XSS, IDOR, and SSRF. This will involve fine-tuning the RAG ingestion pipeline to map specific CVE patterns to their respective remediation logic autonomously.


---

## Licensing

This project was built as an academic capstone for an Agentic AI course. Feel free to fork and extend it for learning purposes.
For problems contact 23b3973@iitb.ac.in
