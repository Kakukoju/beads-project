// src/hooks/use-toast.ts
import * as React from "react"
import type { ToastActionElement, ToastProps } from "@/components/ui/toast"

const TOAST_LIMIT = 1
const TOAST_REMOVE_DELAY = 1000

export type Toast = Omit<ToastProps, "id"> & {
  id: string
  title?: React.ReactNode
  description?: React.ReactNode
  action?: ToastActionElement
}

const listeners: Array<(toasts: Toast[]) => void> = []
let toasts: Toast[] = []
let count = 0

function genId() {
  count = (count + 1) % Number.MAX_SAFE_INTEGER
  return count.toString()
}

function dispatch(toast: Partial<Toast>) {
  const id = toast.id ?? genId()
  toasts = [
    { ...toast, id } as Toast,
    ...toasts
  ].slice(0, TOAST_LIMIT)
  listeners.forEach((l) => l(toasts))
  return id
}

export function toast(props: Omit<Toast, "id">) {
  return dispatch(props)
}

export function useToast() {
  const [state, setState] = React.useState<Toast[]>(toasts)

  React.useEffect(() => {
    listeners.push(setState)
    return () => {
      const idx = listeners.indexOf(setState)
      if (idx >= 0) listeners.splice(idx, 1)
    }
  }, [])

  const dismiss = React.useCallback((id?: string) => {
    toasts = id ? toasts.filter((t) => t.id !== id) : []
    listeners.forEach((l) => l(toasts))
    if (id) {
      setTimeout(() => {
        listeners.forEach((l) => l(toasts))
      }, TOAST_REMOVE_DELAY)
    }
  }, [])

  return {
    toasts: state,
    toast,
    dismiss,
  }
}
