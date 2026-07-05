---
name: done
description: Run when a phase or task is finished. Marks the phase complete in docs/learning-spec.md and writes a reproducible, beginner-proof tutorial under tutorials/ that captures both the build AND everything we clarified this session. Use this when I say I've finished a phase, that a task is done, or when I type /done.
---

# Finish a phase

I've completed a phase or task (phase number / name, if given: $ARGUMENTS).
Run the completion ritual defined in CLAUDE.md, in this order:

1. **Identify the phase.** Work out which phase/task this covers from "$ARGUMENTS" and
   our recent conversation. If it's ambiguous, ask me before doing anything else.

2. **Verify, don't rubber-stamp.** Check the phase's acceptance criteria in
   `docs/learning-spec.md`. If any are not actually met by what we built, tell me exactly
   what's missing and STOP — do not mark it done.

3. **Mine THIS session's conversation (do this before writing).** Re-read our whole
   conversation for this phase and extract, in my own words where possible:
   - Every question I asked, and the answer we landed on.
   - Every point of confusion, surprise, or "wait, why?" — and what cleared it up.
   - Every problem/bug we hit and how we diagnosed and fixed it (e.g. logs not showing,
     something not found, a setting in the wrong place).
   - Every "why" explanation that wouldn't be obvious to a beginner reading the final code.
   - Any decision where we considered alternatives, and why we chose what we chose.
   These are the most valuable part of the tutorial — they are the spots the next person
   (and future-me) will trip on. The struggle IS the content. Do not silently drop them.

4. **Update progress.** Tick the matching checkbox(es) for that phase in
   `docs/learning-spec.md` and update its status in the dashboard table.

5. **Write the tutorial.** Create `tutorials/phases/<short-name>.md` using
   `tutorials/_TEMPLATE.md`, matching the style of `tutorials/phases/project-setup.md`.
   - Base it ONLY on what we actually built and discussed this session — do not invent
     steps, code, or problems.
   - **Split out cross-cutting material.** If something we covered this session is a reusable
     how-to that isn't tied to this one phase (e.g. dependency management, debugging a tool),
     put it in its own `tutorials/guides/<short-name>.md` instead of bloating the phase
     tutorial — then cross-link the two. The phase tutorial stays focused on the phase;
     guides capture the session asides. (`_TEMPLATE.md` stays at the `tutorials/` root.)
   - Pull the "concept it taught / why it matters" and interview angle from the spec.
   - Fold the step 3 findings into the tutorial so a total beginner could follow it:
     * Put each "why" explanation as a **Why** note next to the step it belongs to.
     * Where I was confused about WHERE something goes (e.g. which file/section a setting
       belongs in), state the exact location explicitly.
     * Put every bug/diagnosis/fix into the **Troubleshooting** section, phrased as
       "symptom → why it happens → fix".
     * Add a short **"Concepts that confused me (and the plain-English answer)"** section
       capturing the conceptual Q&A (e.g. why X matters), in beginner language.
   - **Explain beginner-first, with examples (house style — applies to every Why note,
     Troubleshooting entry, and ESPECIALLY the "Concepts that confused me" section).** For any
     non-obvious concept, follow this shape:
     1. **Start from what I already know** — anchor the new idea to something familiar.
     2. **Introduce the new idea in those same terms** — define every piece of jargon the first
        time it appears; assume no prior knowledge.
     3. **Show concrete, runnable examples** — examples teach better than prose; prefer a short
        REPL snippet or tiny worked case over an abstract description.
     4. **Add an analogy** when it makes the idea stick.
     5. **Only then tie back** to the technical/interview framing.
     Complexity comes LAST, not first. Being thorough and going down to fundamentals is preferred
     over staying abstract — never wave at a concept and move on. (Model: the base-10-vs-base-2
     "ruler" explanation of `Decimal` vs `float` — familiar ground → binary place values → worked
     examples → ruler analogy → the interview one-liner.)

6. **Show me before finishing.** Present the new tutorial and the updated checkboxes for
   my review, and briefly list which questions/confusions from the session you folded in,
   so I can confirm nothing important was missed. Do not commit anything unless I ask.
