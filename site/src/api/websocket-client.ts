const WS_BASE_URL: string = import.meta.env.VITE_WS_URL ?? 'ws://127.0.0.1:8000/api'

export interface JsonSocketHandlers {
  onOpen?: () => void
  onMessage: (data: unknown) => void
  onClose?: (event: CloseEvent) => void
  onError?: () => void
}

export interface JsonSocket {
  send: (message: unknown) => void
  close: () => void
}

export function openJsonSocket(path: string, handlers: JsonSocketHandlers): JsonSocket {
  const socket = new WebSocket(`${WS_BASE_URL}${path}`)
  socket.onopen = () => handlers.onOpen?.()
  socket.onclose = (event) => handlers.onClose?.(event)
  socket.onerror = () => handlers.onError?.()
  socket.onmessage = (event) => {
    try {
      handlers.onMessage(JSON.parse(String(event.data)))
    } catch {
      handlers.onError?.()
    }
  }
  return {
    send: (message) => {
      if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message))
    },
    close: () => socket.close(),
  }
}
