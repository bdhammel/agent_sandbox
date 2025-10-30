import { HttpAgent } from 'https://cdn.skypack.dev/@ag-ui/client'

// Message display types and functions
interface DisplayMessage {
  role: 'user' | 'assistant'
  content: string
}

/**
 * Create DOM element for a display message.
 */
function createMessageElement(message: DisplayMessage): HTMLDivElement {
  const div = document.createElement('div')
  div.className = `border-top pt-2 ${message.role}`
  div.textContent = message.content
  return div
}

/**
 * Render a secret_plan custom event.
 */
function renderSecretPlan(steps: string[]): HTMLDivElement {
  const planDiv = document.createElement('div')
  planDiv.className = 'border-top pt-2'
  
  const alertDiv = document.createElement('div')
  alertDiv.className = 'alert alert-info'
  alertDiv.setAttribute('role', 'alert')
  
  const revealBtn = document.createElement('button')
  revealBtn.className = 'btn btn-sm btn-primary'
  revealBtn.textContent = 'Click to reveal'
  
  revealBtn.onclick = () => {
    alertDiv.innerHTML = `
      <strong>🔍 Secret Plan Detected:</strong>
      <ol class="mb-0 mt-2">
        ${steps.map((step: string) => `<li>${step}</li>`).join('')}
      </ol>
    `
  }
  
  alertDiv.appendChild(revealBtn)
  planDiv.appendChild(alertDiv)
  return planDiv
}

const conversation = document.getElementById('conversation') as HTMLDivElement
const promptInput = document.getElementById('prompt-input') as HTMLInputElement
const form = document.querySelector('form') as HTMLFormElement
const spinner = document.getElementById('spinner')
const errorDiv = document.getElementById('error')
const jsonDisplay = document.getElementById('json-display')
const btnAgUi = document.getElementById('btn-ag-ui')
const btnPydanticAi = document.getElementById('btn-pydantic-ai')
const conversationSelect = document.getElementById('conversation-select') as HTMLSelectElement

// Generate initial conversation ID and create agent with it
let currentConversationId = `conv-${Date.now()}`
let agent = new HttpAgent({
  url: '/chat/',
  threadId: currentConversationId,
})

// Load conversations on page load
async function loadConversations() {
  try {
    const response = await fetch('/conversations/')
    if (response.ok) {
      const conversations = await response.json()
      
      // Clear existing options except the "New Conversation" option
      const newConvOption = conversationSelect.options[0]
      conversationSelect.innerHTML = ''
      conversationSelect.appendChild(newConvOption)
      
      // Add all conversations
      conversations.forEach((convId: string) => {
        const option = document.createElement('option')
        option.value = convId
        option.textContent = convId
        conversationSelect.appendChild(option)
      })
      
      // Select current conversation if it exists in the list
      if (conversations.includes(currentConversationId)) {
        conversationSelect.value = currentConversationId
      }
    }
  } catch (error) {
    console.error('Error loading conversations:', error)
  }
}

// Handle conversation selection
conversationSelect.onchange = async () => {
  const selectedId = conversationSelect.value
  
  if (!selectedId) {
    // New conversation - generate new ID and update agent
    currentConversationId = `conv-${Date.now()}`
    conversation.innerHTML = ''
    agent = new HttpAgent({
      url: '/chat/',
      threadId: currentConversationId,
    })
    return
  }
  
  // Load existing conversation
  try {
    spinner.classList.add('active')
    
    // Fetch both agent state and display messages in parallel
    const [rehydrateResponse, displayMessagesResponse] = await Promise.all([
      fetch('/rehydrate/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: selectedId })
      }),
      fetch(`/display-messages/?conversation_id=${selectedId}`)
    ])
    
    if (!rehydrateResponse.ok || !displayMessagesResponse.ok) {
      throw new Error('Failed to load conversation')
    }
    
    // Parse ag_ui messages for agent state (SSE format)
    const agUiText = await rehydrateResponse.text()
    const agUiJsonStr = agUiText.replace(/^data: /, '')
    const agUiEvent = JSON.parse(agUiJsonStr)
    
    // Parse display messages (JSON format)
    const displayMessages = await displayMessagesResponse.json()
    
    currentConversationId = selectedId
    
    // Clear conversation display and create agent with selected conversation ID
    conversation.innerHTML = ''
    agent = new HttpAgent({
      url: '/chat/',
      threadId: selectedId,
    })
    
    // Set agent messages from MessagesSnapshotEvent (after creating agent)
    agent.messages = agUiEvent.messages
    console.log('Agent rehydrated with', agent.messages.length, 'messages')
    
    // Render display messages
    displayMessages.forEach((msg: any) => {
      if (msg.role === 'event' && msg.content) {
        const eventContent = msg.content
        
        // Handle CUSTOM events with name="secret_plan"
        if (eventContent.type === 'CUSTOM' && eventContent.name === 'secret_plan') {
          const planElement = renderSecretPlan(eventContent.value)
          conversation.appendChild(planElement)
        }
        // Add more event type handlers here as needed
        
      } else if (msg.role === 'user' || msg.role === 'assistant') {
        const messageElement = createMessageElement({
          role: msg.role,
          content: msg.content || ''
        })
        conversation.appendChild(messageElement)
      }
      // Skip tool messages and other message types
    })
    
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
  } catch (error) {
    console.error('Error loading conversation:', error)
    errorDiv.classList.remove('d-none')
  } finally {
    spinner.classList.remove('active')
  }
}

// Load conversations on startup
loadConversations()

// Display AG UI messages
btnAgUi.onclick = () => {
  jsonDisplay.textContent = JSON.stringify(agent.messages, null, 2)
}

// Fetch and display Pydantic AI messages from database for current conversation
btnPydanticAi.onclick = async () => {
  try {
    const response = await fetch(`/messages/?conversation_id=${currentConversationId}`)
    if (response.ok) {
      const pydanticAiMessages = await response.json()
      jsonDisplay.textContent = JSON.stringify(pydanticAiMessages, null, 2)
    } else {
      jsonDisplay.textContent = `Error fetching messages: ${response.status}`
    }
  } catch (error) {
    jsonDisplay.textContent = `Error: ${error}`
    console.error(error)
  }
}

form.onsubmit = async (e) => {
  e.preventDefault()
  const prompt = promptInput.value.trim()
  if (!prompt) return

  promptInput.value = ''
  promptInput.disabled = true
  spinner.classList.add('active')

  // Show user message
  const userDiv = document.createElement('div')
  userDiv.className = 'border-top pt-2 user'
  userDiv.textContent = prompt
  conversation.appendChild(userDiv)

  // Add to agent history
  agent.messages.push({
    id: crypto.randomUUID(),
    role: 'user',
    content: prompt,
  })

  // Prepare assistant response div
  let response = ''
  const assistantDiv = document.createElement('div')
  assistantDiv.className = 'border-top pt-2 assistant'
  conversation.appendChild(assistantDiv)

  try {
    await agent.runAgent(
      { threadId: agent.threadId },
      {
        onMessagesSnapshotEvent({ event }: any) {
          console.log('Messages snapshot received:', event)
          // Agent automatically updates its internal state with these messages
        },
        onTextMessageContentEvent({ event }: any) {
          response += event.delta
          assistantDiv.textContent = response
          window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
        },
        onCustomEvent({ event }: any) {
          if (event.name === 'secret_plan') {
            const planElement = renderSecretPlan(event.value)
            conversation.appendChild(planElement)
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
          }
        },
        onRunFinishedEvent({ event }: any) {
          console.log('Agent Messages:', agent.messages)
          spinner.classList.remove('active')
          promptInput.disabled = false
          promptInput.focus()
          // Reload conversations to show current conversation in dropdown
          loadConversations()
        }
      }
    )
  } catch (error) {
    console.error(error)
    assistantDiv.textContent = `Error: ${error}`
    errorDiv.classList.remove('d-none')
    spinner.classList.remove('active')
    promptInput.disabled = false
  }
}
