import re
with open('agent_workflow/query.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the while True loop with a function
new_content = content.replace('while True:\n    print("\\n" + "="*50)\n    query = input("Enter a query to start investigation (or \'q\' to quit): ")\n    query = query.strip(\'\\"\\\'\\\\\')\n    \n    if query.lower() in [\'q\', \'quit\']:\n        print("Exiting session. Goodbye!")\n        break\n        \n    if not query:\n        continue', 
'''def execute_query(query: str, session_history: list = None) -> tuple[dict, list]:
    if session_history is None:
        session_history = []
''')

# We need to indent everything that was inside the while True block
lines = new_content.split('\n')
in_function = False
final_lines = []
for i, line in enumerate(lines):
    if line.startswith('def execute_query('):
        in_function = True
    if in_function and line.startswith('    # -----------------------------') and 'CLASSIFY' in line:
        pass # from here on, we ensure it's 4 spaces indented
    
    # Actually, replacing using string manipulation is safer.
