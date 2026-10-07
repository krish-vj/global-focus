# Global Focus 🛡️

**Global Focus (Study Guard v2)** is a Windows study companion that helps you stay focused across browsers and desktop applications.

It monitors the active foreground window and uses the **Jev (TypeSafe)** decision model through OpenRouter to determine whether you're studying, transitioning between tasks, or getting distracted.

When Block Mode is enabled, distractions are blocked or minimized. Observer Mode lets you monitor your activity without interrupting you.

## Features

- **Cross-app monitoring**  
  Works across Chrome, Edge, Firefox, Brave, IDEs, and other Windows applications.

- **AI-based activity classification**  
  Uses the Jev (TypeSafe) model through OpenRouter to classify activity as:
  - `on_task`
  - `transitioning`
  - `distracted`

- **Smart navigation handling**  
  Neutral pages such as Google Search, YouTube's homepage, new tabs, and File Explorer are treated as transitions instead of distractions.

- **Block Mode** 🛑  
  Distracting browser tabs are redirected to a local motivational page. Distracting desktop applications are minimized.

- **Observer Mode** 👁️  
  Monitors and records activity without blocking anything.

- **Study categories**  
  Create reusable categories such as:
  - DBMS
  - Operating Systems
  - Computer Architecture
  - Coding & Development
  - Any other subject you want to track

- **Study analytics**  
  Tracks sessions, total study time, and time spent on individual categories using SQLite.

- **Tamper-evident logs**  
  Database entries are linked using an HMAC hash chain, allowing the application to detect modifications to stored records.

- **Optional email reports**  
  Send periodic study reports through SMTP, including study statistics and database integrity information.

- **Local web dashboard**  
  A dark-themed dashboard built with Flask, Vanilla JavaScript, and Chart.js.

- **System tray support**  
  The application can run in the background while the dashboard is accessed through your browser.

---

## Setup

### Requirements

- Windows
- Python 3.10+
- An [OpenRouter API key](https://openrouter.ai/settings/keys)

### 1. Install dependencies

Clone the repository and install the required packages:

```bash
pip install -r requirements.txt
```

### 2. Configure your API key

You can configure the API key from the **Settings** tab after launching the application.

Alternatively, create a `config.json` file in the project root:

```json
{
  "ApiKey": "sk-or-v1-your-key-here"
}
```

> **Note:** Do not commit your API key or `config.json` containing a real key to GitHub.

### 3. Start Global Focus

The easiest way to launch the application on Windows is:

```bat
START_STUDY_GUARD.bat
```

You can also start it directly with Python:

```bash
python app.py
```

Once started, the dashboard will be available at:

**http://localhost:7432**

The application should open the dashboard automatically in your default browser.

---

## Modes

### 🛑 Block Mode

Block Mode actively prevents distractions.

For browser-based distractions, Global Focus redirects the tab to a local `/blocked` page.

For distracting Windows applications, the application is minimized.

### 👁️ Observer Mode

Observer Mode does not interfere with your workflow.

It simply monitors the active application and records how your time is being spent.

This is useful when you want to understand your study habits before enabling blocking.

---

## How Classification Works

Global Focus periodically checks the currently active foreground window and sends the relevant information to the Jev model through OpenRouter.

The model classifies the activity into one of three states:

```text
on_task
transitioning
distracted
```

The application then decides what to do based on the current mode.

```text
Active Window
     │
     ▼
Global Focus
     │
     ▼
Jev (TypeSafe)
     │
     ├── on_task ────────► Allow
     │
     ├── transitioning ─► Allow
     │
     └── distracted ────► Block / Minimize
```

Navigation and other neutral activities are intentionally treated as `transitioning` so that normal workflows aren't constantly interrupted.

---

## Analytics

Study data is stored locally in SQLite.

Global Focus records information such as:

- Study sessions
- Session duration
- Study category
- Active application
- Classification results
- Lifetime study time

The dashboard uses this data to provide an overview of your study habits and category-wise progress.

---

## Database Integrity

Global Focus uses an **HMAC hash chain** for its local logs.

Each entry is cryptographically linked to the previous entry. This allows the application to detect modifications, deletions, or forged records in the chain.

The integrity status can also be included in optional reports.

This is intended as a **tamper-evident mechanism**, not as protection against an attacker who completely controls the machine and application environment.

---

## Email Reports

Email reporting is optional.

You can configure SMTP credentials, such as a Gmail App Password, to receive periodic study summaries.

Reports can include:

- Total study time
- Category breakdown
- Session statistics
- Database integrity verification

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python / Flask |
| AI Classification | Jev (TypeSafe) via OpenRouter |
| Database | SQLite |
| Frontend | HTML / CSS / Vanilla JavaScript |
| Charts | Chart.js |
| Desktop Monitoring | Windows APIs |
| Email | SMTP |
| Integrity | HMAC hash chain |

---

## Project Structure

```text
Global-Focus/
├── app.py
├── config.json
├── requirements.txt
├── START_STUDY_GUARD.bat
├── ...
└── README.md
```

---

## Security Notes

- Keep your OpenRouter API key private.
- Do not commit real API keys or SMTP credentials.
- The HMAC chain provides tamper **detection**, not absolute tamper **prevention**.
- Anyone with full control over the machine can potentially modify the application itself and bypass its protections.

---

## License

Add your project's license information here.
