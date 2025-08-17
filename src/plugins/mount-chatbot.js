// src/plugins/mount-chatbot.js
import Vue from 'vue'
import ChatBot from '../components/ChatBot.vue'

let mounted = false

function doMount(root) {
  if (mounted) return
  mounted = true

  const dock = document.createElement('div')
  dock.id = 'chatbot-dock'
  // keep the bot inside the sidebar at the bottom
  dock.style.position = 'absolute'
  dock.style.left = '0'
  dock.style.right = '0'
  dock.style.bottom = '0'
  root.appendChild(dock)

  // eslint-disable-next-line no-new
  new Vue({
    render: h => h(ChatBot)
  }).$mount('#chatbot-dock')
}

export function mountChatBot() {
  // Sidebar root per your file: <div class="nav-side-menu col-lg-2">
  const root = document.querySelector('.nav-side-menu.col-lg-2')
  if (root) return doMount(root)

  // If sidebar is not in DOM yet, watch until it appears
  const obs = new MutationObserver(() => {
    const r = document.querySelector('.nav-side-menu.col-lg-2')
    if (r) {
      obs.disconnect()
      doMount(r)
    }
  })
  obs.observe(document.body, { childList: true, subtree: true })
}
