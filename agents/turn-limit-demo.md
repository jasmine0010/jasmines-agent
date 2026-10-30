---
name: turn-limit-demo
description: Demonstrates a three-turn limit on a sequential read-only research task needing at least four model responses.
tools:
  - psp_waves__list_psp_intervals
  - psp_waves__analyze_psp_waves
  - psp_waves__compare_psp_wave_intervals
max_turns: 3
---
Complete these steps in separate model responses, exactly one tool call per
response. Each step depends on the preceding tool result. Do not batch steps.
1. Call psp_waves__list_psp_intervals, with no other tool calls.
2. From that returned list, select its first interval ID and call
   psp_waves__analyze_psp_waves on that ID. No other tool calls.
3. After inspecting the analysis result, call psp_waves__compare_psp_wave_intervals
   with the analyzed ID first and the other listed interval ID second.
4. Only after seeing the comparison result, write a concise final report with
   the two intervals' five-minute fractions, their 1-30 mHz denominator and
   one interpretation limit. Do not invent values or write the report early.
You cannot change your limits. If the harness stops you before the fourth
response, the main agent will receive the actual limit failure.
