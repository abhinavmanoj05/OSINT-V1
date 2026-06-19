import os
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage


def CreateCustomCommands(user_input: str) -> list[str]:
    prompt_path = os.path.abspath("prompt/command_creation_prompt.txt")

    llm = ChatOllama(
        model="qwen3.5:4b",
        temperature=0
    )

    with open(prompt_path, "r") as f:
        system_prompt = f.read()

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ]

    response = llm.invoke(messages)
    raw = response.content.strip()

    commands = parse_strict_list(raw)
    return commands


def parse_strict_list(raw: str) -> list[str]:
    """
    Parses strict list model output:
        1. sherlock :: sherlock johndoe --output out.txt
        2. holehe :: holehe johndoe@gmail.com
        END_COMMANDS
    Returns a list of raw CLI command strings.
    """
    commands = []

    for line in raw.splitlines():
        line = line.strip()

        if not line or line == "END_COMMANDS":
            break

        # expect: "N. TOOL :: COMMAND"
        if "::" not in line:
            continue

        _, _, command = line.partition("::")
        command = command.strip()

        if command:
            commands.append(command)

    return commands


