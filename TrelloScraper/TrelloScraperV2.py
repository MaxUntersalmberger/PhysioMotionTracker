import os
import requests
import sys
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Resolve the exact path to the directory containing this script
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, '.env')

# Load the file explicitly and force override
if not load_dotenv(dotenv_path=env_path, override=True):
    print(f"FATAL: Could not locate or read .env file at {env_path}", file=sys.stderr)
    sys.exit(1)

TRELLO_API_KEY = os.environ.get("TRELLO_API_KEY")
TRELLO_API_TOKEN = os.environ.get("TRELLO_API_TOKEN")
BOARD_ID = os.environ.get("TRELLO_BOARD_ID")

def fetch_board_data():
    """Fetches normalized board data (cards, lists, members) in a single request."""
    if not all([TRELLO_API_KEY, TRELLO_API_TOKEN, BOARD_ID]):
        print("Error: TRELLO_API_KEY, TRELLO_API_TOKEN, and TRELLO_BOARD_ID must be set in the .env file.", file=sys.stderr)
        sys.exit(1)

    url = f"https://api.trello.com/1/boards/{BOARD_ID}"
    headers = {"Accept": "application/json"}
    
    # Extract all necessary relational data. Added 'id' and 'dateLastActivity' to card_fields.
    query = {
        'key': TRELLO_API_KEY,
        'token': TRELLO_API_TOKEN,
        'lists': 'open',
        'list_fields': 'name',
        'cards': 'open',
        'card_fields': 'id,name,desc,idList,idMembers,dateLastActivity',
        'members': 'all',
        'member_fields': 'fullName',
        'fields': 'name' 
    }

    try:
        response = requests.get(url, headers=headers, params=query, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"API Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    return response.json()

def process_and_export_tasks(board_data, filename="trello_export.xlsx"):
    """Maps relational IDs to names, parses dates, and exports to Excel."""
    
    lists_map = {lst['id']: lst['name'] for lst in board_data.get('lists', [])}
    members_map = {mem['id']: mem.get('fullName', 'Unknown User') for mem in board_data.get('members', [])}
    
    cards = board_data.get('cards', [])
    if not cards:
        print("No cards found on this board.")
        return

    processed_tasks = []

    for card in cards:
        task_name = card.get('name', '')
        description = card.get('desc', '')
        
        list_id = card.get('idList')
        list_name = lists_map.get(list_id, 'Unknown List')
        
        member_ids = card.get('idMembers', [])
        member_names = [members_map.get(m_id, 'Unknown User') for m_id in member_ids]
        assigned_to = ", ".join(member_names) if member_names else "Unassigned"

        # Parse Creation Date from MongoDB ObjectId (First 8 hex characters)
        card_id = card.get('id', '')
        try:
            created_timestamp = int(card_id[:8], 16)
            created_at = datetime.fromtimestamp(created_timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            created_at = 'Unknown'

        # Format Last Activity Date
        last_activity_raw = card.get('dateLastActivity', '')
        last_activity = ''
        if last_activity_raw:
            try:
                # Trello returns ISO 8601 with 'Z' for UTC. Strip it for parsing.
                last_activity_obj = datetime.fromisoformat(last_activity_raw.replace('Z', '+00:00'))
                last_activity = last_activity_obj.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                last_activity = last_activity_raw # Fallback to raw string if parsing fails

        processed_tasks.append({
            'Name': task_name,
            'Description': description,
            'Assigned to': assigned_to,
            'List name': list_name,
            'Created At': created_at,
            'Last Modified': last_activity
        })

    # Load into DataFrame
    df = pd.DataFrame(processed_tasks)

    # Enforce structure and sort
    df = df[['Name', 'Description', 'Assigned to', 'List name', 'Created At', 'Last Modified']]
    df.sort_values(by=['List name'], inplace=True)

    # Export
    try:
        df.to_excel(filename, index=False, engine='openpyxl')
        print(f"Successfully exported {len(df)} tasks to {filename}.")
    except Exception as e:
        print(f"Failed to write Excel file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    data = fetch_board_data()
    process_and_export_tasks(data)