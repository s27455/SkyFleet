# AI-Assisted Development Workflow

This document describes how SkyFleet was built with AI tools: who did what, how a feature went from
idea to commit, and how the results were checked. It is based on my own account as the project
owner and on what the repository records: the Claude Code configuration in `.claude/`, the feature
specifications in `docs/features/`, the progress tracker and the Git history.

## 1. Overview

Two AI tools were used, for different jobs:

- **ChatGPT**: requirements and design discussion. I explained a feature's business logic and
  expected behaviour, we explored options, and once I had decided on the direction, ChatGPT turned
  the decisions into a structured feature brief for Claude Code.
- **Claude Code**: planning against the real codebase, implementation, tests and documentation.
  It worked inside a fixed project context (Section 2) and followed project-specific skills
  (Section 4). For part of the project it also used two read-only review agents (Section 3).

As the project owner, I defined the requirements and approved the outcomes. Claude Code carried
out a substantial portion of the implementation, testing and documentation work. Section 6 sets out
the division of responsibilities in full.

The project was built iteratively, one numbered feature at a time. Each feature has a
specification in `docs/features/`, and many of them end with an implementation record of what was
built, what was verified and what was not.

## 2. Project foundation: seven core documents

Before any feature work, the project context was written down in seven documents in `context/`.
Six were added in the first feature commit (`50ebf03`), and `business-rules.md` followed in
`39fd505`. They are listed in [`CLAUDE.md`](../CLAUDE.md), the root instruction file
that Claude Code loads automatically, as the source of truth. CLAUDE.md also tells Claude which
document to read before which kind of change.

| Document | Responsibility | How it was used |
|---|---|---|
| [`context/project-overview.md`](../context/project-overview.md) | Product vision, business concept, workflows, MVP scope | Kept features tied to the B2B drone-delivery concept and the MVP boundary |
| [`context/business-rules.md`](../context/business-rules.md) | Confirmed business rules and open business questions | Authoritative for behaviour. Plans had to cite it, and Claude was told not to re-raise questions already answered there or to present its own assumptions as approved rules |
| [`context/architecture-context.md`](../context/architecture-context.md) | Architecture, technologies, domain boundaries, integrations | Basis for the modular monolith, the separate Simulation Worker and backend ownership of state; consulted before structural changes |
| [`context/code-standards.md`](../context/code-standards.md) | Coding conventions, implementation and testing expectations | Applied during implementation and by the review agents |
| [`context/ui-context.md`](../context/ui-context.md) | UI/UX direction, design principles, Tailwind guidelines | Read before frontend work, to keep the map-first operations look consistent |
| [`context/ai-workflow-rules.md`](../context/ai-workflow-rules.md) | How the AI assistant must work: understand first, plan before coding, small verifiable steps, no invented requirements | The behavioural contract for Claude Code; the skills in Section 4 put it into practice |
| [`context/progress-tracker.md`](../context/progress-tracker.md) | Roadmap, phases, status, open decisions | Checked before choosing or starting a feature, and updated when one was finalized |

The documents were kept up to date as decisions changed. Larger decisions were also recorded as
ADRs in [`docs/decisions/`](decisions/) (0001–0015). Because every session started from the same
documents, later features followed the same rules as the first ones, without re-explaining the
project in each prompt.

## 3. Claude Code agents

Two subagents are defined in `.claude/agents/` (added in `39fd505`):

- **`code-reviewer`** independently reviews a change for correctness, maintainability,
  architecture, security and scope creep. It checks domain boundaries, backend authority over
  state, deterministic simulation, API contracts and missing tests. It reports only findings
  backed by evidence, ranked by severity.
- **`qa-tester`** independently checks an implemented feature against its acceptance criteria. It
  maps each criterion to code or test evidence and separates confirmed defects from risks and
  unverified areas.

Both agents are **read-only**: they have only Read, Glob and Grep, cannot run commands, and are
told never to claim that tests passed. Each one preloads a matching skill that defines its review
method and report format (`agent-code-review` and `agent-qa-testing`, in `.claude/skills/agent-skills/`).

**Confirmed use.** Several implementation records describe agent runs and their findings, for
example:
- Feature 003: both agents were run twice.
- Features 006 and 009: the code reviewer found Medium issues, which were fixed.
- Feature 011: QA confirmed all 8 acceptance criteria, and two Medium review findings were fixed.

Features 002–009 and 011 record both agents being run, as their specifications required.

**Selective use later on.** From Feature 012 onwards, most implementation records state explicitly
that no QA or code-review agent was run. Examples are 012, the 014 dispatch series, the 015 order
generation series, the 016 inspector series and 019A/019B. Verification for those features relied
on automated checks and my own live testing in the browser. The agents were a tool to bring in when
a feature needed an extra independent check, not a mandatory step for every change.

## 4. Custom skills

Repeated procedures were written as Claude Code skills in `.claude/skills/`, so that every feature
went through the same steps with the same approval gates.

| Skill | Purpose and the steps it standardizes |
|---|---|
| **`feature-start`** (`/feature-start 019`) | Finds the numbered specification. Checks Git for uncommitted work or an unexpected branch, and reports it without changing anything. Reads `CLAUDE.md`, the progress tracker and only the context documents and code the feature touches. Produces a plan through `task-planning`, covering dependencies, risks and verification mapped to the acceptance criteria. Then **stops for my explicit approval**. It never starts implementing, even after approval. |
| **`task-planning`** | Read-only analysis that ends in a fixed plan format: understanding, current state, scope and exclusions, files, ordered steps, verification, and genuine open decisions. It prefers the smallest solution that works. |
| **`task-implementation`** | Runs only after explicit approval. Re-reads the plan and implements only the approved scope in small steps, preserving unrelated changes. Adds or updates tests, runs the narrowest checks first and then broader ones, compares the final diff with the plan, and reports which checks passed, failed or were not run. If the plan has to change materially, it stops and explains why. |
| **`feature-finalization`** | Closes a feature **after I have explicitly approved it as complete**, as described in Section 5. |
| **`documentation-update`** | Updates only the documents affected by a verified change. It separates implemented, tested, planned and proposed work, and never invents endpoints, results or decisions. |
| **`skyfleet-start`** | A convenience command that starts the local development environment (Docker, PostgreSQL, API, worker, Vite) and reports status. It never runs migrations or kills processes. |

The two agent-only skills, `agent-code-review` and `agent-qa-testing`, are described in Section 3.

## 5. Feature development lifecycle

```text
 business idea
      |
      v
 ChatGPT discussion  <-------------------------------+
      |                                              |
      v                                              |
 feature brief (docs/features/NNN-*.md)              |
      |                                              |
      v                                              |
 /feature-start  ->  Claude Code plan  ->  my review -+  (concerns go back for discussion)
                                              |
                                          approved
                                              v
                        implementation (task-implementation)
                                              |
                                              v
          verification: automated checks, live testing,
          review agents when needed  ----------------------> fixes / back to discussion
                                              |
                                          I approve
                                              v
                        /feature-finalization  ->  git commit
```

**A. Requirements (ChatGPT).** I described the feature's business problem, the user experience I
wanted and the behaviour I expected. ChatGPT proposed approaches and pointed out technical
implications. I questioned its assumptions, changed requirements and iterated until I was satisfied.
I then asked it to write a structured brief: goal, operator experience, rules, scope, out of scope,
and acceptance criteria. Many specifications in `docs/features/` show this shape, with explicit
instructions to Claude such as "Claude must propose the smallest coherent mission/flight/drone state and API changes
…" followed by "This precise state model still requires approval in the revised plan" (Feature
010).

**B. Planning (Claude Code).** The brief was saved as a numbered specification, and
`/feature-start` produced a plan grounded in the actual code. Claude Code also had to report
conflicts between the brief, the documentation and the code instead of resolving them silently. I
reviewed the plan. When something looked wrong, or a better option came up, I took it back to
ChatGPT, decided, and brought the decision back. Several specifications record such approved
adjustments at the top (for example 019B: "Approved adjustment (supersedes conflicting text
below)").

**C. Implementation (Claude Code).** After approval, Claude Code implemented the feature across the
stack. Depending on the feature, that meant:
- backend models, migrations, services and endpoints
- worker logic
- frontend components and API clients
- tests
- documentation such as the README, the ADRs and the specification's implementation record

Larger features were split into stages with a checkpoint in between. For example, Feature 010 was
built backend first, followed by a stop for review before the frontend stage.

**D. Verification.** Testing happened inside each feature, not at the end of the project. The depth
varied with the feature:
- Automated checks after every implementation: Pytest (including opt-in PostgreSQL tests for
  locking behaviour), Vitest with React Testing Library, Ruff, strict mypy, oxlint, Prettier,
  TypeScript type checking and production builds. The implementation records state the results,
  and which checks were not run.
- My own live testing in the browser for most features from Feature 018 onwards. Records say, for
  example, "Live QA passed per the owner". Where I asked for changes after testing, those were
  implemented before finalization.
- The review agents for the early features and when extra assurance was useful (Section 3).
- The AI features (024–026) were built in gated steps with written gate records. They were verified
  offline with fake transports, and one paid smoke test was run in Feature 024.
- Back to ChatGPT when behaviour was unexpected or a design question came up.

**E. Finalization.** After I approved a feature as complete, `/feature-finalization`:
1. Confirmed the approval.
2. Collected the verification evidence, re-running checks if the code had changed since.
3. Listed open findings and limitations, stopping if anything blocking remained.
4. Updated the specification's implementation record and the progress tracker through
   `documentation-update`.
5. Inspected `git status` and the diff for unrelated or sensitive files.
6. Reported whether the feature was ready to commit.

The skill **never commits**. The commit was a separate, explicit step that I asked for afterwards.
The cycle then started again with the next feature.

## 6. Responsibilities

**Project owner (me)**
- Defined the business goals, the domain and the functional requirements.
- Reviewed technical decisions and chose between the approaches.
- Reviewed implementation plans before implementation and requested changes.
- Validated the application's behaviour.
- Approved outcomes: decided when a feature was accepted, finalized and committed.

**ChatGPT**
- Brainstorming and refining requirements.
- Comparing architectural and technical options.
- Turning agreed decisions into structured feature briefs for Claude Code.
- Problem-solving and design discussion when issues came up during review or testing.

**Claude Code**
- Inspected the codebase and proposed implementation plans.
- Implemented the approved features, carrying out a substantial portion of the application code,
  tests, migrations and documentation in this repository.
- Ran the automated checks and reported their results, including failures and checks not run.
- Used the project's skills and, when needed, the review agents.

## 7. Verification and lessons learned

### What worked
- **Shared context instead of one-off prompts.** The seven context documents and `CLAUDE.md` kept
  terminology, architecture and business rules consistent across 46 specifications.
- **Business decisions stayed separate from implementation.** Requirements were settled before
  Claude Code started, and open business questions were tracked in `business-rules.md` instead of
  being decided silently in code.
- **Plans were reviewable.** Nothing was implemented without an approved plan. The approval gates
  are written into the skills themselves.
- **The lifecycle was repeatable.** Start, plan, implement, verify, finalize and commit happened the
  same way for each feature.
- **Traceability.** Every feature has a specification, many with an implementation record. Larger
  decisions have ADRs, and the larger commits name the feature they complete.

### Personal retrospective — lessons learned

SkyFleet was my first project of this scale, and it grew considerably beyond what I initially expected. Building a more complex application with extensive AI assistance was both a productive experience and an important lesson in software engineering discipline.

#### The value of AI-assisted development

The biggest advantage was the speed at which I could turn ideas into working functionality. The combination of ChatGPT for discussing requirements and technical approaches, and Claude Code for planning and implementation, worked particularly well during the early stages.

Claude Code was often remarkably effective at solving implementation problems and connecting different parts of the system. The amount of functionality completed within the available time would have been extremely difficult for me to achieve through manual development alone.

This experience made me much more interested in using AI tools in future projects.

#### When speed became a problem

The same speed also created risks.

Early in development, I spent considerable time defining the project's foundations: writing the seven core context documents, planning the architecture, establishing development rules, and preparing diagrams. I initially reviewed implementations closely and understood the code being introduced.

As the project grew and deadlines approached, I sometimes became less thorough. There were occasions when I accepted an implementation after limited verification or postponed a concern with the intention of addressing it later. Fatigue and time pressure contributed to this.

Those shortcuts accumulated. Some issues that could have been caught during the original feature work required additional investigation and correction near the end of the project.

In hindsight, I should have maintained the same level of code review and hands-on verification throughout development, even when the AI-generated solutions appeared convincing.

#### Context management across two AI tools

Using ChatGPT and Claude Code together was initially a deliberate choice. I wanted to separate discussions about business requirements and technical design from implementation work, partly because I was concerned about token consumption and the cost of longer Claude sessions.

However, the two tools did not share a complete, continuously synchronized understanding of the project.

As requirements evolved, one conversation could be based on assumptions that were no longer accurate in the codebase. Even with seven foundational context documents, specifications and implementation decisions sometimes drifted apart.

This created additional coordination work and occasionally contributed to inconsistencies that had to be resolved later.

For future projects, I would consider a more consolidated workflow, potentially centered on one primary development assistant, while keeping the repository documentation as the authoritative source of project context.

#### Architectural decisions and their consequences

One decision I would reconsider is the use of HTTP polling rather than WebSockets for live simulation updates.

The current approach works and keeps the communication model relatively straightforward, but I have noticed occasional visual stuttering in the drone simulation. I believe a push-based update mechanism could be worth exploring for a smoother real-time experience.

I cannot claim that WebSockets alone would solve every animation issue without profiling and testing. Nevertheless, this is an example of an architectural trade-off that I would investigate earlier in a future project rather than postponing until the application had grown.

#### AI-assisted engineering is not the same as vibe coding

One of my most important takeaways is the distinction between using AI as an engineering tool and simply accepting generated code because it appears to work.

At the beginning of SkyFleet, I approached AI-assisted development systematically: defining requirements, reviewing plans, understanding the code, testing behavior, and recording decisions.

Later, under time pressure, parts of my workflow moved closer to what is commonly called *vibe coding*: relying more heavily on generated output and spending less time examining its implementation details.

I do not consider that a sustainable approach for professional software development.

AI can accelerate implementation dramatically, but it does not remove the need to understand the architecture, inspect changes, challenge assumptions, verify behavior, and take responsibility for the final result.

#### What I would do differently

For my next project, I would:

- Maintain consistent code review standards throughout development, regardless of deadlines or how convincing an AI-generated solution looks.

- Complete meaningful verification before considering a feature finished, rather than accumulating deferred checks.

- Keep architectural decisions and feature specifications synchronized with the actual codebase.

- Reduce unnecessary context fragmentation between AI tools.

- Revisit performance-sensitive architectural choices earlier, especially where real-time behavior affects the user experience.

- Keep using AI extensively, but treat its speed as an opportunity for better engineering rather than a reason to skip engineering discipline.

Overall, I consider SkyFleet a very positive learning experience. It demonstrated how much a single developer can accomplish with capable AI tools, but also how quickly technical and process debt can accumulate when the pace of implementation exceeds the pace of understanding and verification.

The central lesson I am taking forward is simple: **AI-assisted software engineering should make development more effective, not make engineering judgment optional.**
