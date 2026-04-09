# Knowledge Base Files

## Purpose

These JSON files contain **domain knowledge** that is loaded into the MCP prompt to help the LLM:

1. **Answer user questions directly** without needing to call tools
2. **Improve query formulation** when tools ARE called
3. **Provide context** for better responses

## NOT Used For

- ❌ Agent selection decisions
- ❌ Tool delegation logic
- ❌ Runtime execution decisions

## Usage

The LLM reads this knowledge and uses it to:
- Explain WLC values (0=Idle, 1=Battery Life, 2=Sustained, 3=Bursty, 4=VC)
- Describe power rail connections and debug hints
- Explain ETL dataframe columns and use cases
- Answer "what is..." questions without tool calls

## Files

### power_rail_knowledge_base.json
- SOC power rails (VCCCORE, VCCST, VCCGT, etc.)
- Platform power rails (P_MEMORY, P_DISPLAY, etc.)
- Debug hints and socwatch metrics

### etl_dataframes_knowledge_base.json
- All available ETL dataframes (df_cpu_util, df_wlc, etc.)
- Column descriptions
- Retrieval patterns
- Use cases and examples

## Source

Copied from: `PnP_agents/PnP/knowledge/`

Keep these files in sync with the source when knowledge is updated.
