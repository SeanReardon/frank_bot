# Claudia Chat Integration for Frank_bot

## Overview

Claudia (the software building orchestrator) is getting a new conversational API that allows frank_bot to have discussions about codebases and collaboratively design features before implementing them. This document describes how frank_bot should integrate with this capability.

## The User Experience

When Sean (via ChatGPT or another LLM interface) wants to make changes to a Claudia-managed repository, the flow should feel natural:

1. **Sean says:** "I want to add dark mode to capital-game"
2. **Frank_bot:** Starts a chat with Claudia about the capital-game repo
3. **Claudia responds** (possibly after waiting in queue): "I see capital-game uses CSS custom properties for theming. The current structure is... What kind of dark mode do you want?"
4. **Back-and-forth discussion** about implementation details, architecture choices, etc.
5. **Sean says:** "That sounds good, let's do it"
6. **Frank_bot:** Ends the chat and asks Claudia to create a prompt from the conversation
7. **Frank_bot:** Triggers prompt execution
8. **Frank_bot:** Polls for completion and reports results

## New Claudia API Endpoints

All endpoints accept `X-API-Key` header for authentication. The key will be stored in Vault.

### Chat Operations

```
POST   /api/repos/{repoId}/chats              # Start a new chat
GET    /api/repos/{repoId}/chats/{chatId}     # Get chat with messages
POST   /api/repos/{repoId}/chats/{chatId}/messages  # Add a message
POST   /api/repos/{repoId}/chats/{chatId}/end       # End the chat
```

### Prompt Operations

```
POST   /api/repos/{repoId}/prompts            # Create prompt from chat
POST   /api/repos/{repoId}/prompts/{id}/execute  # Execute a prompt
GET    /api/repos/{repoId}/prompts            # List prompts (existing)
GET    /api/repos/{repoId}/prompts/{id}       # Get prompt (existing)
```

### Queue & Status

```
GET    /api/repos/{repoId}/queue              # See queue status
GET    /api/executions/{executionId}          # Track execution progress
GET    /api/repos                             # List repos (includes queue info)
```

## Important: The Queue

Claudia uses a **unified queue per repository**. When you start a chat, it goes into the queue behind any pending work. This is intentional - it ensures the user has an accurate understanding of the repo's current state.

**Key behaviors:**
- Creating a chat returns a queue position (e.g., "You're #3 in line")
- You can add messages while waiting - they accumulate
- When the chat reaches the head, Claudia processes accumulated messages
- New messages are processed immediately while the chat is active
- The queue is **blocked** until the user explicitly ends the chat

Frank_bot should communicate queue status naturally:
- "There are 2 PRD tasks ahead of us. I'll process your question when we reach the front, but feel free to keep telling me about the feature you want."
- "We're now at the front of the queue. Let me look at the codebase..."

## Response Codes to Handle

- **200** - Message processed immediately (chat was active)
- **202** - Message queued (chat not yet at head of queue)
- **409** - Conflict (e.g., trying to delete active chat)

## Integration Suggestions for Frank_bot

### 1. New Jorb Type: `claudia_chat`

Consider creating a jorb type specifically for Claudia conversations. This jorb would:
- Start a chat when created
- Route incoming messages to Claudia
- Track queue position
- Handle the chat → prompt → execution lifecycle
- Report final results

### 2. Natural Language Routing

When Sean mentions wanting to change something in a repo, frank_bot should:
1. Identify which Claudia-managed repo is being discussed
2. Ask if Sean wants to start a conversation with Claudia about it
3. Create the chat and manage the back-and-forth

### 3. Queue Awareness

Frank_bot should be aware of and communicate:
- Current queue position
- When the chat becomes active
- When other work is blocking the chat

### 4. Graceful Degradation

If Claudia is unreachable or the chat API isn't available yet:
- Fall back to just discussing the feature with Sean
- Help Sean write a prompt manually
- Sean can then push the prompt to GitHub directly

## Example Conversation Flow

```
Sean: I want to add a feature to capital-game that shows historical portfolio values

Frank: Capital-game is managed by Claudia. Want me to start a conversation with her about this?

Sean: Yes

Frank: [POST /api/repos/{id}/chats]
       Starting a chat with Claudia about capital-game. 
       There's 1 task ahead of us in the queue - I'll let you know when we reach the front.
       
       In the meantime, tell me more about the historical portfolio feature. 
       What timeframe are you thinking?

Sean: I want to see a chart of my portfolio value over the last 30 days

Frank: [POST /api/repos/{id}/chats/{id}/messages → 202 Accepted]
       Got it - 30 day history as a chart. I've queued that for Claudia.
       
       [2 minutes later, polling shows chat is now active]
       
       We're now at the front of the queue. Claudia is looking at the codebase...
       
       [Poll for response]
       
       Claudia says: "I see capital-game has a Chart component using D3 in 
       src/components/Chart.ts. The portfolio value is currently calculated in 
       GameEngine.ts. For historical data, we'd need to either store snapshots 
       or recalculate from transaction history. Which approach do you prefer?"

Sean: Let's store snapshots - recalculating would be slow

Frank: [POST /api/repos/{id}/chats/{id}/messages → 200 with response]
       Claudia says: "Makes sense. I'd suggest adding a portfolio_snapshots table 
       that stores daily snapshots. The bat can add this to the game loop..."
       
       [... more back and forth ...]

Sean: That sounds good, let's do it

Frank: [POST /api/repos/{id}/chats/{id}/end]
       [POST /api/repos/{id}/prompts {chatId: "..."}]
       
       I've ended our chat and asked Claudia to create a prompt from our conversation.
       It's queued for generation. I'll let you know when it's ready.
       
       [Poll /api/repos/{id}/queue until prompt_generation completes]
       
       The prompt has been created and pushed to capital-game. 
       Want me to have Claudia execute it now?

Sean: Yes

Frank: [POST /api/repos/{id}/prompts/{id}/execute]
       
       The prompt is queued for execution. I'll track the progress and 
       let you know when Claudia has implemented the feature.
       
       [Poll /api/executions/{id} until complete]
       
       Done! Claudia has implemented the portfolio history feature. 
       Here's what changed:
       - Added portfolio_snapshots table migration
       - Modified GameEngine.ts to create daily snapshots
       - Added PortfolioHistoryChart component
       - Updated the dashboard to include the new chart
       
       You can see the commit here: [GitHub link]
```

## Configuration

Frank_bot will need:
- `CLAUDIA_API_URL` - Base URL for Claudia API (e.g., `https://claudia.contrived.com`)
- `CLAUDIA_API_KEY` - API key for authentication (store in Vault)

## Phased Rollout

This is a significant feature for Claudia to implement. The integration on frank_bot's side can be built in phases:

**Phase 1:** Basic chat lifecycle (create, message, end)
**Phase 2:** Prompt creation from chat
**Phase 3:** Prompt execution and tracking
**Phase 4:** Rich status reporting and queue awareness

Start with Phase 1 once the Claudia API is available, and iterate from there.
