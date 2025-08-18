<template>
    <div class="chatbot">
        <div class="messages" ref="messages">
            <div
                v-for="(m, idx) in messages"
                :key="idx"
                :class="m.role === 'user' ? 'bubble user' : 'bubble bot'"
            >
                {{ m.text }}
            </div>
        </div>

        <div class="composer">
            <input
                v-model="input"
                class="composer-input"
                type="text"
                placeholder="Type a message…"
                @keyup.enter="sendMessage"
            >
            <button class="composer-send" @click="sendMessage">Send</button>
        </div>
    </div>
</template>

<script>
import axios from 'axios'

export default {
    name: 'ChatBot',
    data () {
        return {
            messages: [],
            input: '',
            sessionId: this.restoreSession()
        }
    },
    methods: {
        restoreSession () {
            try {
                const s = window.localStorage.getItem('chat_session_id')
                if (s) return s
            } catch (e) {}
            const id = `session-${Math.random().toString(36).slice(2)}`
            try {
                window.localStorage.setItem('chat_session_id', id)
            } catch (e) {}
            return id
        },

        pushBot (text) {
            this.messages.push({ role: 'bot', text })
            this.$nextTick(() => {
                const el = this.$refs.messages
                if (el) el.scrollTop = el.scrollHeight
            })
        },

        async sendMessage () {
            const userText = (this.input || '').trim()
            if (!userText) return

            this.messages.push({ role: 'user', text: userText })
            this.input = ''

            try {
                // Build payload with bracket keys to satisfy camelcase rule
                /* eslint-disable camelcase, dot-notation */
                const payload = {
                    session_id: this.sessionId,
                    user_message: userText,
                    include_digest: true
                }
                /* eslint-enable camelcase, dot-notation */

                // Must match your proxy (/api/chat -> agent-dev:8787/chat)
                const res = await axios.post('/api/chat', payload, { timeout: 60000 })

                const arr = Array.isArray(res.data && res.data.messages)
                    ? res.data.messages
                    : []

                const assistant = arr.find(m => m && m.role === 'assistant')
                const botText = assistant && (assistant.content || assistant.text)

                this.pushBot(botText || 'No reply received from agent.')

                if (res.data && res.data.session_id) {
                    this.sessionId = res.data.session_id
                    try {
                        window.localStorage.setItem('chat_session_id', this.sessionId)
                    } catch (e) {}
                }
            } catch (err) {
                const status = err && err.response && err.response.status
                    ? ` ${err.response.status}`
                    : ''
                const msg = err && err.message ? ` ${err.message}` : ''
                this.pushBot(`Error from agent:${status}${msg}`)
            }
        }
    }
}
</script>

<style scoped>
.chatbot {
    display: flex;
    flex-direction: column
}

.messages {
    height: 260px;
    overflow-y: auto;
    padding: 8px;
    background: #1f2838;
    border-radius: 8px
}

.bubble {
    max-width: 85%;
    padding: 8px 12px;
    margin: 6px 0;
    border-radius: 12px;
    line-height: 1.3
}

.bubble.user {
    margin-left: auto;
    background: #4a6cff;
    color: #fff
}

.bubble.bot {
    margin-right: auto;
    background: #e9eef7;
    color: #1b1f2a
}

.composer {
    display: flex;
    gap: 8px;
    margin-top: 8px
}

.composer-input {
    flex: 1;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 8px
}

.composer-send {
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
    background: #334155;
    color: #fff;
    cursor: pointer
}

.composer-send:hover {
    opacity: .9
}
</style>
