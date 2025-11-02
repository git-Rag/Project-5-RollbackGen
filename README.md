
---

# **Configuration Backup & Rollback Tool — Project 5**

This repository contains a portfolio-ready demo of **Configuration Backup & Rollback Tool**, a Python project that lets you **save configuration states (in JSON)** and **restore them later** if changes cause issues. It’s a safe, minimal system backup utility that teaches the foundation of **SafeCore’s rollback and recovery system**.

---

## **What is included**

**Core Idea:**
Design a mini tool that saves configurations or states (in JSON files) before changes, and can restore them if needed.

**Concepts Covered:**
File handling, JSON operations, functions, error handling, backups, and versioning.

**Relevance to SafeCore:**
This project demonstrates the foundation of SafeCore’s rollback feature — ensuring user safety during configuration enforcement by keeping reliable state backups.

---

## **Run locally**

1. Create a Python environment *(Python 3.10+ recommended)*.

2. Run the following command to install dependencies (if any):

   ```bash
   pip install -r requirements.txt
   ```

   *(This script only uses Python’s standard library, so this step is optional.)*

3. Create a sample configuration file:

   ```bash
   echo '{ "settingA": true, "threshold": 42, "nested": { "mode": "safe" } }' > sample_config.json
   ```

   *(Use single quotes `'...'` on PowerShell or paste JSON manually in a file.)*

4. Run the tool to create a backup:

   ```bash
   python config_backup_tool.py backup sample_config.json
   ```

5. Restore a backup anytime:

   ```bash
   python config_backup_tool.py restore sample_config.json
   ```

---

## **Example Workflow**

```bash
# Create initial config
python config_backup_tool.py backup sample_config.json

# Make edits or break something...

# Then rollback safely
python config_backup_tool.py restore sample_config.json
```

---

## **Project Structure**

```
│
├── config_backup_tool.py   # Main backup & restore logic
├── sample_config.json      # Example configuration file
├── backups/                # Folder where backups are saved
│   └── sample_config_backup.json
└── README.md               # Project documentation
```
