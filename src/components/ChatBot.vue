<template>
  <div class="chatbot-panel" :class="{ open: isOpen }">
    <div class="chatbot-header" @click="toggle">
      <span>💬 Flight Chat</span><small v-if="!isOpen">click to open</small>
    </div>
    <div class="chatbot-body" v-if="isOpen">
      <div class="chatbot-messages" ref="scroll">
        <div v-for="(m, idx) in messages" :key="idx" :class="['msg', m.role]">
          <pre>{{ m.content }}</pre>
        </div>
      </div>
      <div class="chatbot-footer">
        <b-form-textarea v-model="text" rows="2" max-rows="4"
          placeholder="Ask about altitude, GPS loss, battery temp, flight time, anomalies..." />
        <div class="actions">
          <b-form-checkbox v-model="includeTelemetry">Send telemetry digest</b-form-checkbox>
          <b-button variant="primary" size="sm" :disabled="loading || !text.trim()" @click="send">Send</b-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { store } from './Globals'
import { v4 as uuidv4 } from 'uuid'

export default {
  name: 'ChatBot',
  data () { return { isOpen: true, text: '', messages: [], includeTelemetry: true, loading: false, sessionId: uuidv4() } },
  methods: {
    toggle () { this.isOpen = !this.isOpen; this.$nextTick(this.scrollToEnd) },
    scrollToEnd () { const el = this.$refs.scroll; if (el) el.scrollTop = el.scrollHeight },
    async send () {
      if (!this.text.trim()) return
      const userMsg = { role: 'user', content: this.text.trim() }
      this.messages.push(userMsg); this.text = ''; this.loading = true
      try {
        const base = process.env.VUE_APP_AGENT_BASE_URL || 'http://localhost:8787'
        let telemetry = null
        if (this.includeTelemetry) {
          telemetry = { messages: {} }
          const N = 500
          const msgs = store.messages || {}
          Object.keys(msgs).forEach(k => { const arr = Array.isArray(msgs[k]) ? msgs[k] : []; telemetry.messages[k] = arr.slice(0, N) })
        }
        const res = await fetch(`${base}/chat`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: this.sessionId, user_message: userMsg.content, telemetry, include_digest: true })
        })
        const json = await res.json()
        this.messages = json.messages || this.messages
        this.sessionId = json.session_id || this.sessionId
        this.$nextTick(this.scrollToEnd)
      } catch (e) { this.messages.push({ role: 'assistant', content: `Error contacting agent: ${e}` }) }
      finally { this.loading = false }
    }
  }
}
</script>

<style scoped>
.chatbot-panel { position: absolute; left: 0; bottom: 0; width: 100%; max-height: 40%;
  background: rgba(12,16,24,0.92); border-top: 1px solid rgba(255,255,255,0.06);
  color: #eef3f7; font-size: 12px; transition: transform .2s ease-in-out; transform: translateY(0%) }
.chatbot-panel:not(.open) { transform: translateY(calc(100% - 28px)) }
.chatbot-header { display:flex; justify-content:space-between; align-items:center; padding:6px 10px;
  background: rgba(255,255,255,0.04); cursor: pointer; user-select: none; font-weight: 600 }
.chatbot-body { display:flex; flex-direction:column; height: calc(100% - 28px) }
.chatbot-messages { flex:1; overflow:auto; padding:8px 10px }
.msg { margin-bottom: 8px; white-space: pre-wrap }
.msg.user pre { background: rgba(255,255,255,0.05); padding: 6px 8px; border-radius: 6px }
.msg.assistant pre { background: rgba(0,153,255,0.08); padding: 6px 8px; border-radius: 6px }
.chatbot-footer { padding: 6px 8px; border-top: 1px solid rgba(255,255,255,0.06) }
.actions { display:flex; align-items:center; justify-content:space-between; margin-top:6px }
</style>
