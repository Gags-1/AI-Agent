from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
import json
import requests
import os
import webbrowser
import subprocess

# Load environment variables
load_dotenv()

genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))

model = genai.GenerativeModel('gemini-2.0-flash')

current_working_directory = os.getcwd()
background_processes = []

def run_command(cmd: str):
    """Execute shell command, background dev servers (npm start/dev) handled."""
    global current_working_directory

    try:
        if cmd.strip().startswith("cd "):
            parts = cmd.strip().split("&&")
            dir_to_cd = parts[0].strip()[3:].strip()
            if os.path.isdir(dir_to_cd):
                current_working_directory = os.path.abspath(dir_to_cd)
                return f"Changed working directory to: {current_working_directory}"
            else:
                return f"Directory does not exist: {dir_to_cd}"

        # Detect dev server command
        if any(kw in cmd for kw in ["npm start", "vite", "npm run dev"]):
            process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=current_working_directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            background_processes.append(process)
            return f"Started background process for: `{cmd}`"

        # Normal command
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=current_working_directory
        )
        if result.returncode == 0:
            return f"Command '{cmd}' executed successfully.\nOutput:\n{result.stdout.strip()}"
        else:
            return f"Command '{cmd}' failed.\nStderr:\n{result.stderr.strip()}"

    except subprocess.TimeoutExpired:
        return f"Command '{cmd}' timed out after 120 seconds."
    except Exception as e:
        return f"Error executing command '{cmd}': {e}"

def get_weather(city: str):
    try:
        url = f"https://wttr.in/{city}?format=%C+%t"
        response = requests.get(url)
        response.raise_for_status()
        return f"The weather in {city} is {response.text.strip()}."
    except Exception as e:
        return f"Error fetching weather: {e}"

def create_file(file_path: str, content: str):
    try:
        full_path = os.path.join(current_working_directory, file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"File '{full_path}' created."
    except Exception as e:
        return f"Error creating file '{file_path}': {e}"

def create_folder(folder_path: str):
    try:
        full_path = os.path.join(current_working_directory, folder_path)
        os.makedirs(full_path, exist_ok=True)
        return f"Folder '{full_path}' created."
    except Exception as e:
        return f"Error creating folder '{folder_path}': {e}"

def read_file(file_path: str):
    try:
        full_path = os.path.join(current_working_directory, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return f"Content of '{file_path}':\n{f.read()}"
    except Exception as e:
        return f"Error reading file '{file_path}': {e}"

def list_folder_contents(folder_path: str = '.'):
    try:
        full_path = os.path.join(current_working_directory, folder_path)
        contents = os.listdir(full_path)
        if not contents:
            return f"Folder '{full_path}' is empty."
        return f"Contents of '{full_path}':\n" + "\n".join(contents)
    except Exception as e:
        return f"Error listing folder '{folder_path}': {e}"

def launch_browser(url: str):
    try:
        webbrowser.open(url)
        return f"Opened browser at: {url}"
    except Exception as e:
        return f"Error opening browser: {e}"

available_tools = {
    "get_weather": get_weather,
    "run_command": run_command,
    "create_file": create_file,
    "create_folder": create_folder,
    "read_file": read_file,
    "list_folder_contents": list_folder_contents,
    "launch_browser": launch_browser
}

SYSTEM_PROMPT = """
You are a helpful AI Assistant who is specialized in resolving user query.
You work on start, plan, action, observe mode.

For the given user query and available tools, plan the step by step execution. Based on the planning,
select the relevant tool from the available tools. Based on the tool selection, you perform an action to call the tool.

Wait for the observation, and based on the observation from the tool call, resolve the user query.

Rules:
- Follow the Output JSON Format.
- Always perform one step at a time and wait for the next input.
- Carefully analyze the user query.
- When building web applications, use create_folder, run_command (like `npx create-react-app`, `npm create vite@latest`, `npm install`, `npm start`) and create_file to scaffold projects.
- After building and starting a dev server, use launch_browser to open it (usually at localhost).

Output JSON Format:
{
    "step": "string",
    "content": "string",
    "function": "The name of function if the step is action",
    "input": "The input parameter for the function"
}
"""

messages = [
    {"role": "user", "parts": [{"text": SYSTEM_PROMPT}]}
]

while True:
    query = input("> ")
    messages.append({"role": "user", "parts": [{"text": query}]})

    while True:
        try:
            response = model.generate_content(
                messages,
                generation_config={"response_mime_type": "application/json"}
            )

            assistant_response_content = response.text
            messages.append({"role": "model", "parts": [{"text": assistant_response_content}]})
            parsed_response = json.loads(assistant_response_content)

            if parsed_response.get("step") == "plan":
                print(f"🧠: {parsed_response.get('content')}")
                continue

            if parsed_response.get("step") == "action":
                tool_name = parsed_response.get("function")
                tool_input = parsed_response.get("input")

                print(f"🛠️: Calling Tool: {tool_name} with input '{tool_input}'")

                if tool_name in available_tools:
                    if tool_name == "create_file":
                        if isinstance(tool_input, dict) and "file_path" in tool_input and "content" in tool_input:
                            output = available_tools[tool_name](tool_input["file_path"], tool_input["content"])
                        else:
                            output = f"Error: Invalid input for create_file."
                    else:
                        output = available_tools[tool_name](tool_input)

                    messages.append({"role": "user", "parts": [{"text": json.dumps({"step": "observe", "output": output})}]})
                    continue
                else:
                    print(f"❌ Tool '{tool_name}' not found.")
                    messages.append({"role": "user", "parts": [{"text": json.dumps({"step": "observe", "output": f"Tool '{tool_name}' not found."})}]})
                    continue

            if parsed_response.get("step") == "output":
                print(f"🤖: {parsed_response.get('content')}")
                break

        except json.JSONDecodeError:
            print("❌ Error: Model returned non-JSON response. Retrying...")
            if messages and messages[-1]["role"] == "model":
                messages.pop()
            continue
        except Exception as e:
            print(f"🔥 Unexpected Error: {e}")
            break
