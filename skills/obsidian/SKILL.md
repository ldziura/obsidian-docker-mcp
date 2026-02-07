---
name: obsidian
description: Read notes from a folder in the Obsidian vault. Loads the vault's CLAUDE instructions and all notes from the specified folder into context.
argument-hint: [folder-path] [optional instructions]
allowed-tools: mcp__obsidian__obsidian_get_file_contents, mcp__obsidian__obsidian_list_files_in_dir, mcp__obsidian__obsidian_list_files_in_vault, mcp__obsidian__obsidian_simple_search, mcp__obsidian__obsidian_complex_search, mcp__obsidian__obsidian_patch_content, mcp__obsidian__obsidian_append_content, mcp__obsidian__obsidian_delete_file, mcp__obsidian__obsidian_batch_get_file_contents, mcp__obsidian__obsidian_get_periodic_note, mcp__obsidian__obsidian_get_recent_periodic_notes, mcp__obsidian__obsidian_get_recent_changes
---

# Obsidian Vault Reader

You are working with an Obsidian vault via the Obsidian MCP server.

## Step 1: Load vault instructions

Use `obsidian_get_file_contents` to read `CLAUDE.md` from the vault root. This file contains critical instructions about vault structure, formatting rules, and how to use tools like `obsidian_patch_content`. You MUST follow all instructions in that file for any vault operations.

## Step 2: Parse the arguments

The full argument string is: **$ARGUMENTS**

Parse this into two parts:
- **Folder path**: The first token (e.g., `01_Projects`, `03_Resources/Japanese`). This is always the first space-separated segment — or multiple segments if it's a path with no spaces.
- **User instructions**: Everything after the folder path. This is what the user wants you to do after loading the notes.

If the argument only contains a folder path with no additional instructions, proceed to Step 4 (present context and ask what to do).

## Step 3: List and read all notes in the target folder

1. Use `obsidian_list_files_in_dir` with the parsed folder path to get all files in the folder.
2. If the folder contains subfolders, recursively list their contents too.
3. Use `obsidian_batch_get_file_contents` to read all `.md` files found. If there are many files, batch them in groups.

## Step 4: Act on instructions or present context

**If the user provided instructions** (e.g., "and reorganize the notes", "summarize them", "find todos"):
- Execute those instructions using the loaded context and vault rules.

**If no instructions were provided:**
- Provide a brief summary of what was loaded (number of notes, filenames, key themes).
- Ask the user what they'd like to do with these notes.

You now have full context of the folder contents and vault instructions to assist with any operations (editing, creating, reorganizing, searching, etc.).

## Key rules from the vault

- Use **wikilinks** (`[[Note Name]]`) for internal links, not markdown links
- Always preserve existing frontmatter and update `modified` date when editing
- For `obsidian_patch_content`, nested heading targets use `::` separator (e.g., `"Section A::Subsection 1"`)
- Place new notes in `00_Inbox/` when unsure of destination
- Use PARA structure: Projects, Areas, Resources, Archive
