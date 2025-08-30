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
/* eslint-disable */
import axios from 'axios'
import { store } from '@/components/Globals'

// Toggle verbose telemetry debug
const DEBUG_TELEMETRY = true
const dbg = (...args) => { if (DEBUG_TELEMETRY) console.log('[TEL]', ...args) }
const warn = (...args) => { if (DEBUG_TELEMETRY) console.warn('[TEL]', ...args) }

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
        // Treat both Arrays and TypedArrays as series
        _isArrayLike (v) {
          // true for Array and all *Array views (Float32Array, Uint16Array, etc.)
          return (Array.isArray(v) || (v && typeof v === 'object' && typeof v.length === 'number' && ArrayBuffer.isView && ArrayBuffer.isView(v)))
        },
        _toArray (v) {
          if (!v) return []
          if (Array.isArray(v)) return v
          // TypedArray -> plain Array
          if (ArrayBuffer.isView && ArrayBuffer.isView(v)) return Array.from(v)
          return []
        },
        // Dump keys for a candidate message object (handles flat object or array-of-objects)
        _dumpMsgShape(label, msgObj) {
          try {
            if (!msgObj) { warn(label, 'no msgObj'); return }
            if (Array.isArray(msgObj)) {
              const first = msgObj.find(o => o && typeof o === 'object') || {}
              dbg(label, 'array-of-objects keys:', Object.keys(first))
            } else if (typeof msgObj === 'object') {
              dbg(label, 'flat keys:', Object.keys(msgObj))
            } else {
              warn(label, 'unexpected msgObj type:', typeof msgObj)
            }
          } catch (e) {
            warn(label, 'shape dump failed:', e)
          }
        },
        __debugResolve (expr, s) {
          const parsed = this.parseExpr(expr)
          const out = { expr, base: null, idx: null, field: null, shape: null, reason: '' }
          if (!parsed) { out.reason = 'parse fail'; return out }
          const { base, index, field } = parsed
          out.base = base; out.idx = index; out.field = field

          console.log()

          const msg = s?.messages?.[base] ?? s?.messages?.[base?.toUpperCase()] ?? s?.messages?.[base?.toLowerCase()]
          if (!msg) {
            // try GPS2/GPA2 style
            if (index !== null) {
              const suff = `${base}${index + 1}`
              const msg2 = s?.messages?.[suff] ?? s?.messages?.[suff.toUpperCase()] ?? s?.messages?.[suff.toLowerCase()]
              if (msg2) {
                out.shape = 'split-per-instance'
                out.reason = Array.isArray(msg2[field]) ? 'OK' : `no field ${field}`
                return out
              }
              // try bracket key
              const bkey = `${base}[${index}]`
              const msg3 = s?.messages?.[bkey]
              if (msg3) {
                out.shape = 'bracket-key'
                out.reason = Array.isArray(msg3[field]) ? 'OK' : `no field ${field}`
                return out
              }
            }
            out.reason = `no message key (${base})`
            return out
          }

          if (Array.isArray(msg)) {
            out.shape = 'array-of-objects'
            const mo = (index !== null) ? msg[index] : msg.find(o => o && typeof o === 'object')
            if (!mo) { out.reason = 'no obj for index'; return out }
            out.reason = Array.isArray(mo[field]) ? 'OK' : `no field ${field}`
            return out
          }

          out.shape = 'flat'
          const hasField = Array.isArray(msg[field])
          const inst = msg.I ?? msg.Instance
          const hasInst = Array.isArray(inst)
          out.reason = hasField ? (index !== null ? (hasInst ? 'OK' : 'no I/Instance') : 'OK')
                                : `no field ${field}`
          return out
        },
        // Parse "MSG[idx].FIELD" or "MSG.FIELD" -> { base, index|null, field }
        parseExpr (expr) {
          const m = String(expr).match(/^([A-Za-z0-9_]+)(?:\[(\d+)\])?\.(.+)$/)
          if (!m) return null
          return { base: m[1], index: m[2] ? Number(m[2]) : null, field: m[3] }
        },

        // ---- BEGIN: telemetry helpers (ChatBot.vue) ----
        getStore () {
          // Be defensive: if the import failed or hasn’t initialized, return an empty object
          try { return store || {} } catch (e) { return {} }
        },

        pickTimeKeyFlexible (msgObj) {
          var preferred = ['TimeUS', 'time_boot_ms', 'timestamp', 't', 'time']
          for (var i = 0; i < preferred.length; i++) {
            var k = preferred[i]
            if (this._isArrayLike(msgObj && msgObj[k])) return k
          }
          // any key containing "time"
          if (msgObj) {
            var ks = Object.keys(msgObj)
            for (var j = 0; j < ks.length; j++) {
              var kk = ks[j]
              if (/time/i.test(kk) && this._isArrayLike(msgObj[kk])) return kk
            }
            // fallback: longest numeric array-like
            var best = null, bestLen = -1
            for (var j2 = 0; j2 < ks.length; j2++) {
              var kx = ks[j2], v = msgObj[kx]
              if (this._isArrayLike(v)) {
                var len = v.length
                if (len > bestLen) { best = kx; bestLen = len }
              }
            }
            return best
          }
          return null
        },

        downsampleXY (x, y, maxPoints = 800) {
          const n = Math.min(x?.length || 0, y?.length || 0)
          if (!n) return { x: [], y: [] }
          if (n <= maxPoints) return { x, y }
          const stride = Math.ceil(n / maxPoints)
          const xs = []; const ys = []
          for (let i = 0; i < n; i += stride) { xs.push(x[i]); ys.push(y[i]) }
          return { x: xs, y: ys }
        },

        // Return current “expressions” the UI intends to show, e.g. ["GPS.Alt", "ATT.Roll"]
        // If UI hasn't set any, we propose a sensible default set from ArduPilot logs.

        getExpressionNamesOrDefaults () {
          const s = this.getStore()
          let exprs = []
          if (Array.isArray(s.expressions)) {
            exprs = s.expressions.map(e => (e && e.name) ? e.name : e).filter(Boolean)
          }
          if (exprs.length) return exprs

          const has = (msg, field) =>
            Array.isArray(s?.messages?.[msg]?.[field]) && s.messages[msg][field].length > 0

          const d = []
          if (has('GPS', 'Alt')) d.push('GPS.Alt')
          if (has('GPS', 'Lat') && has('GPS', 'Lng')) { d.push('GPS.Lat'); d.push('GPS.Lng') }
          if (has('ATT', 'Roll')) d.push('ATT.Roll')
          if (has('ATT', 'Pitch')) d.push('ATT.Pitch')
          if (has('ATT', 'Yaw')) d.push('ATT.Yaw')
          if (has('BARO', 'Alt')) d.push('BARO.Alt')
          if (has('NKF1', 'VN')) d.push('NKF1.VN')
          if (has('NKF1', 'VE')) d.push('NKF1.VE')
          if (has('NKF1', 'VD')) d.push('NKF1.VD')
          if (has('IMU', 'GyrX')) d.push('IMU.GyrX')
          if (has('IMU', 'AccX')) d.push('IMU.AccX')
          return d
        },

        // Build numeric series directly from store.messages for ["MSG.FIELD", ...]
        buildSeriesFromMessages (expressions, maxPoints) {
          maxPoints = maxPoints || 800
          var s = (typeof store !== 'undefined' && store) ? store : {}
          var out = []
          if (!expressions || !expressions.length) return out

          function toSecondsLocal (arr, key) {
            if (!arr) return []
            if (/TimeUS/i.test(key)) return arr.map(function (v) { return v / 1e6 })
            if (/ms/i.test(key))     return arr.map(function (v) { return v / 1e3 })
            return arr
          }
          function downsampleXY (x, y, cap) {
            var n = Math.min(x.length, y.length)
            if (n <= cap) return { x: x, y: y }
            var stride = Math.ceil(n / cap), xs = [], ys = []
            for (var i = 0; i < n; i += stride) { xs.push(x[i]); ys.push(y[i]) }
            return { x: xs, y: ys }
          }

          for (var ei = 0; ei < expressions.length; ei++) {
            var expr = expressions[ei]
            var parsed = this.parseExpr(expr)
            if (!parsed) continue
            var base = parsed.base, index = parsed.index, field = parsed.field

            // Resolve message object (base / split-key / bracket-key)
            var msg = s && s.messages ? (s.messages[base] || s.messages[String(base).toUpperCase()] || s.messages[String(base).toLowerCase()]) : null
            var via = 'base'
            if (!msg && index !== null) {
              var suff = base + String(index + 1)
              msg = s && s.messages ? (s.messages[suff] || s.messages[suff.toUpperCase()] || s.messages[suff.toLowerCase()]) : null
              if (msg) via = 'split-key'
            }
            if (!msg && index !== null && s && s.messages) {
              var bkey = base + '[' + index + ']'
              msg = s.messages[bkey] || null
              if (msg) via = 'bracket-key'
            }
            if (!msg) continue

            // Array-of-objects layout
            if (Array.isArray(msg)) {
              var mo = null
              if (index !== null && msg[index] && typeof msg[index] === 'object') mo = msg[index]
              if (!mo) {
                for (var k = 0; k < msg.length; k++) { if (msg[k] && typeof msg[k] === 'object') { mo = msg[k]; break } }
              }
              if (!mo) continue
              var vArrAO = this._toArray(mo[field])
              if (!vArrAO.length) continue
              var tKeyAO = this.pickTimeKeyFlexible(mo)
              var tArrAO = this._toArray(tKeyAO ? mo[tKeyAO] : null)
              if (!tArrAO.length) continue
              var tSecAO = toSecondsLocal(tArrAO, tKeyAO || '')
              var dsAO = downsampleXY(tSecAO, vArrAO, maxPoints)
              var lenAO = Math.min(dsAO.x.length, dsAO.y.length)
              out.push({ name: expr, axis: 'y', color: undefined, length: lenAO, sample: dsAO.x.map(function (tt, i) { return { t: tt, v: dsAO.y[i] } }) })
              continue
            }

            // Flat (fields → arrays/typedarrays)
            if (msg && typeof msg === 'object') {
              var vAllRaw = msg[field]
              var vAll = this._toArray(vAllRaw)
              if (!vAll.length) continue

              var tKey = this.pickTimeKeyFlexible(msg)
              var tAll = this._toArray(tKey ? msg[tKey] : null)
              if (!tAll.length) continue

              // Only filter by Instance when we resolved the *base* key.
              var t = tAll, v = vAll
              if (index !== null && via === 'base') {
                var instRaw = (typeof msg.I !== 'undefined') ? msg.I : msg.Instance
                var inst = this._toArray(instRaw)
                if (inst.length) {
                  var tf = [], vf = []
                  var n = Math.min(tAll.length, vAll.length, inst.length)
                  for (var i2 = 0; i2 < n; i2++) if (inst[i2] === index) { tf.push(tAll[i2]); vf.push(vAll[i2]) }
                  if (!tf.length) continue
                  t = tf; v = vf
                }
              }

              var tSec = toSecondsLocal(t, tKey || '')
              var ds = downsampleXY(tSec, v, maxPoints)
              var len = Math.min(ds.x.length, ds.y.length)
              out.push({ name: expr, axis: 'y', color: undefined, length: len, sample: ds.x.map(function (tt, i) { return { t: tt, v: ds.y[i] } }) })
              continue
            }
          }

          return out
        },
        // Build the final “plot” payload for the agent (names + samples)
        buildPlotPayloadForAgent () {
          const s = (typeof store !== 'undefined' && store) ? store : {}
          const expressions = this.getExpressionNamesOrDefaults()


          // inside buildPlotPayloadForAgent or your "has" helper
          function has (msg, field) {
            var sLocal = (typeof store !== 'undefined' && store) ? store : {}
            return sLocal && sLocal.messages && sLocal.messages[msg] &&
                   _this._isArrayLike(sLocal.messages[msg][field]) &&
                   sLocal.messages[msg][field].length > 0
          }


          const extras = []
          if (has('GPS','Alt')  && !expressions.includes('GPS.Alt'))  extras.push('GPS.Alt')
          if (has('BARO','Alt') && !expressions.includes('BARO.Alt')) extras.push('BARO.Alt')

          const finalExpr = [...new Set([...expressions, ...extras])]
          const series = this.buildSeriesFromMessages(finalExpr, 800)
          return { expressions: finalExpr, series }
        },
        // ---- END: telemetry helpers (ChatBot.vue) ----

        buildTelemetry () {
            // TODO: replace the example below with your real data source.
            // Example if you keep series in Vuex:
            // const series = this.$store.state.plots?.currentSeries || {}

            // If you have nothing wired yet, return {} — the agent will answer without digest
            const series = {}

            // Normalize to a simple shape the backend expects
            // Return keys that exist for you (time, altitude, airspeed, etc.)
            const telemetry = {}

            if (series.time && Array.isArray(series.time)) telemetry.time = series.time
            if (series.altitude && Array.isArray(series.altitude)) telemetry.altitude = series.altitude
            if (series.airspeed && Array.isArray(series.airspeed)) telemetry.airspeed = series.airspeed

            return telemetry
        },
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
                const plotPayload = this.buildPlotPayloadForAgent()

                dbg('final expressions:', plotPayload.expressions)
                dbg('series count:', plotPayload.series.length)
                if (!plotPayload.series.length) warn('no series — check logs above for field/time/instance reasons')
                try {
                  const s = (typeof store !== 'undefined' && store) ? store : {}
                  console.log('[DBG] message keys:', Object.keys(s.messages || {}))
                  const exprs = plotPayload.expressions || []
                  const report = []
                  for (const e of exprs) {
                    const r = this.__debugResolve(e, s)
                    report.push(r)
                  }
                  console.table(report)
                } catch (e) {
                  console.warn('[DBG] resolution debug failed:', e)
                }

                console.log('sending plotPayload:', plotPayload) // should show series with samples
                const payload = {
                  session_id: this.sessionId,
                  user_message: userText,
                  include_digest: true,
                  digest: { plot: plotPayload }   // <— this is what your server will read
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
