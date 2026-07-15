# AI Assistant Instructions

## IMPORTANT

This project includes a curated set of Agent Skills located in:

.claude/skills/

These skills are part of the project's engineering standards and **must be treated as authoritative guidance**.

Whenever a task falls under one of these domains, you **must consult and follow the corresponding skill before producing an answer, writing code, reviewing code, or suggesting an implementation.**

Do not ignore these skills or substitute your own preferences unless explicitly instructed by the user.

## Installed Skills

The following skills are available and should be applied whenever relevant:

- api-design-principles
- code-review
- database-design
- documentation-standards
- extract-design-system
- frontend-design
- git-advanced-workflows
- skill-creator
- web-design-guidelines

## Mandatory Rules

### API Development

Always follow **api-design-principles** when:

- Designing REST APIs
- Naming endpoints
- Choosing HTTP methods
- Designing request/response schemas
- Error handling
- Status codes
- Pagination
- Validation

---

### Database Design

Always follow **database-design** when:

- Designing schemas
- Creating SQLAlchemy models
- Defining relationships
- Choosing normalization strategies
- Planning migrations

---

### Documentation

Always follow **documentation-standards** when generating:

- README.md
- API documentation
- Architecture documents
- Approach documents
- Inline documentation
- Docstrings

---

### Code Reviews

Whenever modifying existing code or proposing improvements, perform an internal review using the **code-review** skill before returning the final solution.

Look for:

- bugs
- edge cases
- performance issues
- security concerns
- maintainability
- readability

---

### Frontend

If any frontend work is requested, strictly follow:

- frontend-design
- web-design-guidelines

Maintain consistency in:

- layout
- spacing
- typography
- accessibility
- responsive behavior
- component organization

---

### Git

Whenever suggesting commits, branches, PR descriptions, merge strategies, or repository organization, follow **git-advanced-workflows**.

Prefer:

- small logical commits
- meaningful commit messages
- clean branching strategies

---

### Creating New Skills

If a recurring pattern appears that is not covered by the existing skills, use **skill-creator** to propose a reusable project-specific skill instead of repeating instructions across conversations.

---

## Priority Order

When solving problems, use this order of precedence:

1. User instructions
2. Project requirements
3. Relevant installed Agent Skills
4. Language/framework best practices
5. General AI knowledge

If there is a conflict between your default behavior and an installed Agent Skill, **follow the installed Agent Skill** unless the user explicitly overrides it.

## Expected Behaviour

Before writing code:

- Identify which installed skills apply.
- Apply them consistently throughout the implementation.
- Produce production-quality code that complies with those skills.

Never bypass or ignore an applicable installed skill.

## Project-Specific Rule

Before responding to any request, determine whether one or more installed skills are applicable.

If a relevant skill exists under `.claude/skills/`, you MUST follow it before generating code, explanations, reviews, documentation, or architectural decisions.

Treat these skills as the project's engineering standards.

Do not ignore them unless the user explicitly instructs otherwise.