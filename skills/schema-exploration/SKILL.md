---
name: schema-exploration
description: Lists tables, describes columns and data types, identifies foreign key relationships, and maps entity relationships in a database. Use when the user asks about database schema, table structure, column types, what tables exist, ERD, foreign keys, or how entities relate.
---

# Schema Exploration Skill

## Workflow

### 1. List All Tables
Use `sql_db_list_tables` tool to see all available tables in the database.

This returns the complete list of tables you can query.

### 2. Get Schema for Specific Tables
Use `sql_db_schema` tool with table names to examine:
- **Column names** - What fields are available
- **Data types** - INTEGER, TEXT, REAL, etc.
- **Sample data** - example rows to understand content
- **Primary keys** - Unique identifiers for rows
- **Foreign keys** - Relationships to other tables

### 3. Map Relationships
Identify how tables connect:
- `borough` is the shared key across every borough-level table
  (BoroughSummary, BoroughDailyTrend, BoroughRisk)
- `name` (line name) is the shared key between LineStatus and Disruption
- There are no formal FOREIGN KEY constraints defined in this database —
  relationships are implicit through shared column names, so confirm by
  checking `sql_db_schema` on both tables rather than assuming a constraint exists

### 4. Answer the Question
Provide clear information about:
- Available tables and their purpose
- Column names and what they contain
- How tables relate to each other
- Sample data to illustrate content
- Whether the table reflects a live snapshot or a growing history (see
  Quality Guidelines below) — this matters a lot for this database, since
  most tables refresh every 15 minutes

## Example: "What tables are available?"

**Step 1:** Use `sql_db_list_tables`

**Response:**
```
The london_transport.db database has 7 tables:
1. LineStatus - Every monitored line's current status (mode, severity, borough) — live snapshot, refreshed every 15 min
2. Disruption - Only the currently-disrupted lines, with classified root cause — live snapshot
3. BoroughSummary - One row per borough: disruption rate, avg severity, GVA — live snapshot
4. BoroughDailyTrend - One row per borough per calendar day — growing history, use for trend questions
5. DisruptionCause - Incidents grouped by root cause, with average severity — live snapshot
6. ModeSummary - One row per transport mode (tube, dlr, overground, elizabeth-line) — live snapshot
7. BoroughRisk - Composite risk score, risk band, and estimated GVA at risk per borough — live snapshot
```

## Example: "What columns does the BoroughSummary table have?"

**Step 1:** Use `sql_db_schema` with table name "BoroughSummary"

**Response:**
```
The BoroughSummary table has these columns:

- borough (TEXT) - Borough name, e.g. "Camden", "Westminster"
- lines_reported (INTEGER) - Number of distinct lines monitored in this borough
- disrupted_lines (INTEGER) - How many of those lines are currently disrupted
- average_severity (REAL) - Mean TfL severity score (10 = Good Service, lower = worse)
- total_gva_m (REAL) - Borough's Gross Value Added, £ millions (from ONS)
- disruption_rate_pct (REAL) - disrupted_lines / lines_reported * 100

Sample data shows boroughs like:
- Westminster, Camden, Islington, Tower Hamlets, Hackney
```

## Example: "How do I find which boroughs have the worst disruption trend this week?"

**Step 1:** Identify tables needed
- BoroughDailyTrend (has the day-by-day history needed for a trend question)
- Optionally BoroughRisk (has the current composite risk score for context)

**Step 2:** Map relationships
```
BoroughDailyTrend (borough, date)
  ↓ shared key: borough
BoroughRisk (borough, composite_risk_score)
```

**Response:**
```
To find which boroughs have the worst disruption trend this week:
1. Start with BoroughDailyTrend
2. Filter to the last 7 calendar days
3. GROUP BY borough, aggregate disruption_rate_pct (e.g. AVG or MAX)
4. Optionally JOIN to BoroughRisk on borough for current risk context
5. ORDER BY the aggregated disruption rate DESC

This requires the query-writing skill to execute.
```

## Quality Guidelines

**For "list tables" questions:**
- Show all table names
- Add brief descriptions of what each contains
- Note which tables are a **live snapshot** (current moment only — LineStatus,
  Disruption, BoroughSummary, DisruptionCause, ModeSummary, BoroughRisk) vs a
  **growing history** (BoroughDailyTrend) — this distinction changes which
  table is correct for a given question

**For "describe table" questions:**
- List all columns with data types
- Explain what each column contains
- Show sample data for context
- Note the shared key(s) used to join to other tables (there are no declared
  FOREIGN KEY constraints in this database, so state the join key explicitly
  rather than saying "foreign key")

**For "how do I query X" questions:**
- Identify required tables
- Prefer BoroughDailyTrend for anything involving "trend", "over time",
  "history", or a specific date; prefer the current-snapshot tables for
  "right now" / "currently" questions
- Map the JOIN path (usually just `borough` or `name`)
- Suggest next steps (use query-writing skill)
