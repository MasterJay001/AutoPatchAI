import os
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq

async def notify_admin_via_email(vulnerability, patch):
    print("\n--- 📧 DISPATCHING DEPLOYMENT RECEIPT VIA GMAIL MCP ---")
    
    groq_api_key = os.getenv("GROQ_API_KEY")
    # 1. Use the exact server that you know works!
    # 2. Pass os.environ so the child process inherits your system PATH and credentials
    client = MultiServerMCPClient({
        "gmail": {
            "command": "npx",
            "args": ["-y", "@gongrzhe/server-gmail-autoauth-mcp"], 
            "transport": "stdio",
            "env": os.environ 
        }
    })
    
    try:
        # Await the tools initialization
        gmail_tools = await client.get_tools()
        
        # Initialize Groq
        email_llm = ChatGroq(
            model="llama-3.3-70b-versatile", 
            temperature=0.1,
            api_key=groq_api_key
        ).bind_tools(gmail_tools)
        
        # Craft the email
        email_prompt = f"""
        You are the AutoPatchAI reporting agent. 
        TASK: Send an email immediately to 'jayrathod.internship@gmail.com'. 
        
        REQUIRED ACTIONS:
        1. Subject: 'AutoPatchAI Deployed: Security Vulnerability Resolved'
        2. Body: Clearly state a human administrator approved the patch. Include:
           Vulnerability: {vulnerability}
           Patch: {patch}
           
        CRITICAL: Do not just create a draft. Use the 'send' tool to dispatch this email immediately.
        """
        
        response = email_llm.invoke([HumanMessage(content=email_prompt)])
        
        # Execute tool call
        if response.tool_calls:
            for tool_call in response.tool_calls:
                
                for tool in gmail_tools:
                    if tool.name == tool_call["name"]:
                        result = await tool.ainvoke(tool_call["args"])
                        # results
                        print(f"DEBUG: MCP Tool Raw Result: {result}")
        else:
            print("WARNING: The LLM did not generate a tool call to send the email.")
        
    except Exception as e:
        print(f"❌ MCP Connection Error: {e}")
