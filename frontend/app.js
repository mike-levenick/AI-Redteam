/**
 * AI Redteam CTF - Frontend Client
 * Handles UI, SSE streaming, and session management
 */

// Configuration - UPDATE THIS with your Lambda Function URL
const API_BASE_URL = 'http://localhost:5001';  // For local development
// const API_BASE_URL = 'YOUR_LAMBDA_FUNCTION_URL';  // For production

class CTFClient {
    constructor() {
        this.sessionId = null;
        this.userName = 'Anonymous';
        this.currentStage = 1;
        this.eventSource = null;
        this.currentMessageElement = null;
    }

    async createSession(userName) {
        console.log('Fetching:', `${API_BASE_URL}/api/session/create`); // DEBUG
        try {
            const response = await fetch(`${API_BASE_URL}/api/session/create`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ userName })
            });
            console.log('Response received:', response.status, response.statusText); // DEBUG

            if (!response.ok) {
                console.error('Response not OK:', response.status); // DEBUG
                throw new Error('Failed to create session');
            }

            const data = await response.json();
            console.log('Session data:', data); // DEBUG
            this.sessionId = data.sessionId;
            this.userName = data.userName;
            this.currentStage = data.stage;

            // Save session ID to localStorage
            localStorage.setItem('ctf_session_id', this.sessionId);

            return data;
        } catch (error) {
            console.error('Error in createSession:', error); // DEBUG
            throw error;
        }
    }

    async sendMessage(message) {
        // Check if it's a slash command
        if (message.startsWith('/')) {
            return await this.sendCommand(message);
        } else {
            return await this.streamResponse(message);
        }
    }

    async sendCommand(command) {
        const response = await fetch(`${API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sessionId: this.sessionId,
                message: command
            })
        });

        if (!response.ok) {
            if (response.status === 404) {
                throw new Error('SESSION_EXPIRED');
            }
            throw new Error('Command failed');
        }

        const data = await response.json();
        return data;
    }

    async streamResponse(message) {
        return new Promise((resolve, reject) => {
            const url = `${API_BASE_URL}/api/chat/stream?sessionId=${encodeURIComponent(this.sessionId)}&message=${encodeURIComponent(message)}`;

            this.eventSource = new EventSource(url);
            let fullResponse = '';

            // Cold start timeout warning
            const coldStartTimeout = setTimeout(() => {
                showLoadingMessage('Waking up servers... This may take a few seconds.');
            }, 2000);

            this.eventSource.onmessage = (event) => {
                clearTimeout(coldStartTimeout);
                hideLoadingMessage();

                try {
                    const chunk = JSON.parse(event.data);
                    fullResponse += chunk;
                    appendToCurrentMessage(chunk);
                } catch (e) {
                    // If parsing fails, just append the data directly
                    fullResponse += event.data;
                    appendToCurrentMessage(event.data);
                }
            };

            this.eventSource.addEventListener('done', () => {
                clearTimeout(coldStartTimeout);
                hideLoadingMessage();
                this.eventSource.close();
                this.eventSource = null;
                finishMessage();
                resolve(fullResponse);
            });

            this.eventSource.onerror = (error) => {
                clearTimeout(coldStartTimeout);
                hideLoadingMessage();
                this.eventSource.close();
                this.eventSource = null;
                reject(new Error('Stream connection failed'));
            };
        });
    }

    async exportSession() {
        const response = await fetch(`${API_BASE_URL}/api/session/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionId: this.sessionId })
        });

        if (!response.ok) {
            throw new Error('Failed to export session');
        }

        return await response.json();
    }

    async importSession(sessionData) {
        const response = await fetch(`${API_BASE_URL}/api/session/import`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sessionData })
        });

        if (!response.ok) {
            throw new Error('Failed to import session');
        }

        const data = await response.json();
        this.sessionId = data.sessionId;
        this.userName = data.userName;
        this.currentStage = data.stage;

        // Update localStorage
        localStorage.setItem('ctf_session_id', this.sessionId);

        return data;
    }
}

// Global client instance
const client = new CTFClient();

// UI Elements
const welcomeScreen = document.getElementById('welcome-screen');
const chatScreen = document.getElementById('chat-screen');
const userNameInput = document.getElementById('user-name-input');
const startButton = document.getElementById('start-button');
const messagesContainer = document.getElementById('messages');
const messageInput = document.getElementById('message-input');
const sendButton = document.getElementById('send-button');
const stageDisplay = document.getElementById('stage-display');
const sessionIdDisplay = document.getElementById('session-id-display');
const exportButton = document.getElementById('export-session-button');
const importButton = document.getElementById('import-session-button');
const importFileInput = document.getElementById('import-file-input');
const loadingOverlay = document.getElementById('loading-overlay');
const loadingMessage = document.getElementById('loading-message');
const errorModal = document.getElementById('error-modal');
const errorMessage = document.getElementById('error-message');
const errorCloseButton = document.getElementById('error-close-button');

// UI Functions
function showLoading(message = 'Loading...') {
    loadingMessage.textContent = message;
    loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
    loadingOverlay.classList.add('hidden');
}

function showLoadingMessage(message) {
    loadingMessage.textContent = message;
    if (loadingOverlay.classList.contains('hidden')) {
        loadingOverlay.classList.remove('hidden');
    }
}

function hideLoadingMessage() {
    loadingOverlay.classList.add('hidden');
}

function showError(message) {
    errorMessage.textContent = message;
    errorModal.classList.remove('hidden');
}

function hideError() {
    errorModal.classList.add('hidden');
}

function switchToChat() {
    welcomeScreen.classList.add('hidden');
    chatScreen.classList.remove('hidden');
    messageInput.focus();
}

function updateStageDisplay(stage) {
    const stageNames = {
        1: 'The Warmup (Easy)',
        2: 'Basic Resistance (Medium)',
        3: 'Alternate attack surfaces (Hard)',
        4: 'External research (Very Hard)',
        5: 'True Redteam (Expert)'
    };
    stageDisplay.textContent = `STAGE ${stage} of 5: ${stageNames[stage] || 'Unknown'}`;
}

function addMessage(role, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}`;

    const roleLabel = document.createElement('div');
    roleLabel.className = 'message-role';
    roleLabel.textContent = role === 'user' ? 'You' : 'AI';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;

    messageDiv.appendChild(roleLabel);
    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);

    // Scroll to bottom
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    return messageDiv;
}

function addSystemMessage(content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message message-system';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = content;

    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);

    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function startMessage(role) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}`;

    const roleLabel = document.createElement('div');
    roleLabel.className = 'message-role';
    roleLabel.textContent = role === 'user' ? 'You' : 'AI';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.textContent = '';

    messageDiv.appendChild(roleLabel);
    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);

    client.currentMessageElement = contentDiv;

    return messageDiv;
}

function appendToCurrentMessage(text) {
    if (client.currentMessageElement) {
        client.currentMessageElement.textContent += text;
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

function finishMessage() {
    client.currentMessageElement = null;
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function setInputEnabled(enabled) {
    messageInput.disabled = !enabled;
    sendButton.disabled = !enabled;
    if (enabled) {
        messageInput.focus();
    }
}

// Event Handlers
startButton.addEventListener('click', async () => {
    console.log('Start button clicked!'); // DEBUG
    const userName = userNameInput.value.trim() || 'Anonymous';
    console.log('Username:', userName); // DEBUG
    console.log('API URL:', API_BASE_URL); // DEBUG

    showLoading('Creating session...');

    try {
        console.log('Calling createSession...'); // DEBUG
        await client.createSession(userName);
        sessionIdDisplay.textContent = `Session: ${client.sessionId.substring(0, 16)}...`;

        switchToChat();
        setInputEnabled(true);

        addSystemMessage('Welcome to the AI Redteam CTF! Your goal is to extract the secret flag from the AI.');
        addSystemMessage('Type /help for available commands, or just start chatting.');

        hideLoading();
    } catch (error) {
        hideLoading();
        showError('Failed to create session. Please try again.');
    }
});

async function sendUserMessage() {
    const message = messageInput.value.trim();
    if (!message) return;

    // Add user message to UI
    addMessage('user', message);
    messageInput.value = '';
    setInputEnabled(false);

    try {
        if (message.startsWith('/')) {
            // Handle slash command
            const result = await client.sendCommand(message);

            if (result.success) {
                addSystemMessage(result.message);

                // Handle special actions
                if (result.action === 'advance' || result.action === 'win') {
                    client.currentStage = result.currentStage;
                    updateStageDisplay(client.currentStage);
                }
            } else {
                addSystemMessage(result.message);
            }
        } else {
            // Stream regular message
            startMessage('assistant');
            await client.streamResponse(message);
        }
    } catch (error) {
        if (error.message === 'SESSION_EXPIRED') {
            showError('Your session has expired. Please refresh the page to start a new session.');
        } else {
            addSystemMessage(`Error: ${error.message}`);
        }
    } finally {
        setInputEnabled(true);
    }
}

sendButton.addEventListener('click', sendUserMessage);

messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendUserMessage();
    }
});

exportButton.addEventListener('click', async () => {
    try {
        const sessionData = await client.exportSession();

        // Download as JSON file
        const blob = new Blob([JSON.stringify(sessionData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `ctf-session-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);

        addSystemMessage('Session exported successfully!');
    } catch (error) {
        showError('Failed to export session.');
    }
});

importButton.addEventListener('click', () => {
    importFileInput.click();
});

importFileInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
        const text = await file.text();
        const sessionData = JSON.parse(text);

        showLoading('Importing session...');

        await client.importSession(sessionData);

        // Clear UI and update
        messagesContainer.innerHTML = '';
        updateStageDisplay(client.currentStage);
        sessionIdDisplay.textContent = `Session: ${client.sessionId.substring(0, 16)}...`;

        addSystemMessage(`Session imported! You are now on Stage ${client.currentStage}.`);

        hideLoading();
    } catch (error) {
        hideLoading();
        showError('Failed to import session. Make sure the file is a valid CTF session export.');
    }

    // Clear file input
    importFileInput.value = '';
});

errorCloseButton.addEventListener('click', hideError);

// Allow Enter key on name input
userNameInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        startButton.click();
    }
});

// Initialize - check for existing session in localStorage
window.addEventListener('DOMContentLoaded', () => {
    const savedSessionId = localStorage.getItem('ctf_session_id');
    if (savedSessionId) {
        // Could add session restoration here, but for simplicity we'll just clear it
        // Session restoration would require a /api/session/validate endpoint
        localStorage.removeItem('ctf_session_id');
    }
});
