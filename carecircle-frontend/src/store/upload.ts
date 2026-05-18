import { create } from 'zustand'

interface UploadState {
  active_upload_event_id: string | null
  upload_status: string | null
  setUploadEvent: (id: string, status: string) => void
  clearUpload: () => void
}

export const useUploadStore = create<UploadState>()((set) => ({
  active_upload_event_id: null,
  upload_status: null,
  setUploadEvent: (id, status) =>
    set({ active_upload_event_id: id, upload_status: status }),
  clearUpload: () => set({ active_upload_event_id: null, upload_status: null }),
}))
