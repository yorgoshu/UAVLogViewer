<template>
    <div class="chatbot-container">
        <div class="chat-window">
            <div
                v-for="(message, index) in messages"
                :key="index"
                class="message-row"
                :class="message.sender"
            >
                <div class="message-bubble">{{ message.text }}</div>
            </div>
        </div>
        <div class="input-row">
            <input
                v-model="userInput"
                @keyup.enter="sendMessage"
                type="text"
                placeholder="Type your message..."
                class="chat-input"
            />
            <button @click="sendMessage" class="chat-send-btn">Send</button>
        </div>
    </div>
</template>

<script>
/* eslint-disable camelcase, dot-notation */
import axios from 'axios'

export default {
    name: 'ChatBot',
    data () {
        return {
            userInput: '',
            messages: [],
            sessionId: this.generateSessionId()
        }
    },
    methods: {
        generateSessionId () {
            return 'session-' + Math.random().toString(36).substr(2, 9)
        },
        async sendMessage () {
            const userText = this.userInput.trim()
            if (!userText) return

            // Add user message
            this.messages.push({ sender: 'user', text: userText })
            this.userInput = ''

            try {
                // Use snake_case keys to match backend contract (valid identifiers; no quotes needed)
                const body = {
                    session_id: this.sessionId,
                    user_message: userText,
                    include_digest: true
                }

                const response = await axios.post('/api/chat', body)

                if (response && response.data && response.data.reply) {
                    this.messages.push({ sender: 'bot', text: response.data.reply })
                } else {
                    this.messages.push({ sender: 'bot', text: 'No reply received.' })
                }
            } catch (error) {
                /* eslint-disable no-console */
                console.error('Error sending message:', error)
                /* eslint-enable no-console */
                this.messages.push({
                    sender: 'bot',
                    text: '⚠️ Error: Could not connect.'
                })
            }
        }
    }
}
</script>

<style scoped>
.chatbot-container {
    display: flex;
    flex-direction: column;
    height: 100%;
}

.chat-window {
    flex: 1;
    overflow-y: auto;
    padding: 10px;
    border: 1px solid #ccc;
    margin-bottom: 8px;
}

.message-row {
    display: flex;
    margin-bottom: 6px;
}

.message-row.user {
    justify-content: flex-end;
}

.message-row.bot {
    justify-content: flex-start;
}

.message-bubble {
    max-width: 70%;
    padding: 8px 12px;
    border-radius: 14px;
    background-color: #f1f1f1;
    word-wrap: break-word;
}

.message-row.user .message-bubble {
    background-color: #007bff;
    color: #fff;
}

.input-row {
    display: flex;
    border-top: 1px solid #ccc;
    padding: 6px;
}

.chat-input {
    flex: 1;
    padding: 6px;
    border: 1px solid #ccc;
    border-radius: 4px;
}

.chat-send-btn {
    margin-left: 8px;
    padding: 6px 12px;
    border: none;
    background-color: #007bff;
    color: #fff;
    border-radius: 4px;
    cursor: pointer;
}

.chat-send-btn:hover {
    background-color: #0056b3;
}
</style>
