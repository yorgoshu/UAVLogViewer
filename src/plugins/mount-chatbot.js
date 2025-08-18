import Vue from 'vue'
import ChatBot from '../components/ChatBot.vue'

let mounted = false

function doMount (root) {
    if (mounted) return
    mounted = true

    const dock = document.createElement('div')
    dock.id = 'chatbot-dock'
    dock.style.position = 'absolute'
    dock.style.left = '0'
    dock.style.right = '0'
    dock.style.bottom = '0'
    root.appendChild(dock)

    // eslint-disable-next-line no-new
    new Vue({
        render: (h) => h(ChatBot)
    }).$mount('#chatbot-dock')
}

export function mountChatBot () {
    const root = document.querySelector('.nav-side-menu.col-lg-2')
    if (root) {
        doMount(root)
        return
    }

    const obs = new MutationObserver(() => {
        const found = document.querySelector('.nav-side-menu.col-lg-2')
        if (found) {
            obs.disconnect()
            doMount(found)
        }
    })
    obs.observe(document.body, { childList: true, subtree: true })
}
