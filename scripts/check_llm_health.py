import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI

# Load environment variables
load_dotenv()

def print_result(provider: str, success: bool):
    if success:
        print(f"[{provider}] [PASS]")
    else:
        print(f"[{provider}] [FAIL: Authentication/Connection Error]")

def check_groq():
    try:
        if not os.environ.get("GROQ_API_KEY"):
            print_result("Groq", False)
            return

        llm = ChatGroq(model="llama3-8b-8192", temperature=0, max_retries=0)
        response = llm.invoke("Reply with OK")
        if response and response.content:
            print_result("Groq", True)
        else:
            print_result("Groq", False)
    except Exception:
        # Catch all exceptions and explicitly NOT print traceback to avoid leaking keys
        print_result("Groq", False)

def check_google():
    try:
        if not os.environ.get("GOOGLE_API_KEY"):
            print_result("Google", False)
            return

        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0, max_retries=0)
        response = llm.invoke("Reply with OK")
        if response and response.content:
            print_result("Google", True)
        else:
            print_result("Google", False)
    except Exception:
        print_result("Google", False)

def check_mistral():
    try:
        if not os.environ.get("MISTRAL_API_KEY"):
            print_result("Mistral", False)
            return

        llm = ChatMistralAI(model="open-mistral-7b", temperature=0, max_retries=0)
        response = llm.invoke("Reply with OK")
        if response and response.content:
            print_result("Mistral", True)
        else:
            print_result("Mistral", False)
    except Exception:
        print_result("Mistral", False)

if __name__ == "__main__":
    print("Running secure provider health checks...")
    check_google()
    check_groq()
    check_mistral()
