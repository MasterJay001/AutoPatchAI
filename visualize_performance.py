import json
import os
import matplotlib.pyplot as plt

def log_run_to_history(vulnerability_details, retry_count):
    history_file = "history.json"
    run_data = {"vulnerability_details": vulnerability_details, "retry_count": retry_count}
    
    history = []
    if os.path.exists(history_file):
        with open(history_file, 'r') as f:
            history = json.load(f)
            
    history.append(run_data)
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=4)

def generate_performance_graph():
    if not os.path.exists("history.json"):
        print("No history file found!")
        return
    with open("history.json", 'r') as f:
        history = json.load(f)
    
    run_indices = range(1, len(history) + 1)
    retry_counts = [run["retry_count"] for run in history]
    
    plt.figure(figsize=(10, 6))
    plt.bar(run_indices, retry_counts, color='teal')
    plt.title('Agentic Self-Healing Efficiency')
    plt.savefig("performance_metrics.png")
    plt.bar(run_indices, retry_counts, width=0.5)
    plt.show()