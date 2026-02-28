---
name: documentation
description: Documentation Brief description for SEO and navigation
---

### Documentation

The documentation for this project is available in the `docs/` directory. It uses GitHub-flavored markdown and follows the Diátaxis framework for systematic documentation.

## Diátaxis Framework

Documentation must be organized into four distinct types, each serving a specific purpose:

### 1. Tutorials (Learning-Oriented)
**Purpose**: Guide beginners through achieving a specific outcome to build confidence.

- Start with what the user will build or achieve
- Provide a clear, step-by-step path from start to finish
- Include concrete examples and working code
- Assume minimal prior knowledge
- Focus on the happy path (avoid edge cases and alternatives)
- End with a working result the user can see and use
- Use imperative mood: "Create a file", "Run the command"

**Avoid**: Explaining concepts in depth, multiple options, troubleshooting

### 2. How-to Guides (Goal-Oriented)
**Purpose**: Show how to solve a specific real-world problem or accomplish a particular task.

- Title format: "How to [accomplish specific goal]"
- Assume the user knows the basics
- Focus on practical steps to solve one problem
- Include necessary context but stay focused
- Show multiple approaches only when genuinely useful
- End when the goal is achieved
- Use imperative mood: "Configure the setting", "Add the following"

**Avoid**: Teaching fundamentals, explaining every detail, being exhaustive

### 3. Reference (Information-Oriented)
**Purpose**: Provide accurate, complete technical descriptions of the system.

- Organized by structure (CLI commands, configuration options, API endpoints)
- Comprehensive and authoritative
- Consistent format across all entries
- Technical accuracy is paramount
- Include all parameters, options, and return values
- Use descriptive mood: "The command accepts", "Returns a string"
- Minimal narrative or explanation

**Avoid**: Instructions, tutorials, opinions on usage

### 4. Explanation (Understanding-Oriented)
**Purpose**: Clarify and illuminate topics to deepen understanding.

- Discuss why things are the way they are
- Explain design decisions and tradeoffs
- Provide context and background
- Connect concepts to help form mental models
- Discuss alternatives and their implications
- Use indicative mood: "This approach provides", "The engine uses"

**Avoid**: Step-by-step instructions, exhaustive reference material

## General Style Guidelines

- **Tone**: Neutral, technical, not promotional
- **Voice**: Avoid "we", "our", "us" (use "the system", "this module")
- **Headings**: Use markdown heading syntax, not bold text as headings
- **Lists**: Avoid long bullet point lists; prefer prose with structure
- **Code samples**: Minimal and focused; exclude optional fields unless relevant

## Content to Avoid

- "Key Features" sections
- Marketing language or selling points
- Excessive bullet points (prefer structured prose)
- Overly verbose examples with all optional parameters
- Mixing documentation types (e.g., tutorials that become reference)
