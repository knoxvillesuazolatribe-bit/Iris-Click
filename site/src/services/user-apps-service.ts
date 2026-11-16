import { z } from 'zod'
import { isAxiosError } from 'axios'
import { apiClient } from '@/api/api-client'
import { appClient } from '@/api/app-client'
import { ONLINE_COPY } from '@/lib/online-copy'

/** Customizable Apps tiles (extension). Launching is by tile id only. */
const tileSchema = z.object({
  tile_id: z.number(),
  label: z.string(),
  kind: z.enum(['builtin', 'installed_app', 'website']),
  icon: z.string(),
  note: z.string().nullable(),
  available: z.boolean(),
  problem: z.string().nullable(),
})
export type AppTile = z.infer<typeof tileSchema>

const tilesSchema = z.object({
  tiles: tileSchema.array(),
  hidden_defaults: z.object({ tile_id: z.number(), label: z.string(), icon: z.string() }).array(),
  max_tiles: z.number(),
  suggestions: z.object({ label: z.string(), url: z.string(), icon: z.string() }).array(),
})
export type AppTiles = z.infer<typeof tilesSchema>

const installedSchema = z.object({ name: z.string(), path: z.string() })
export type InstalledApp = z.infer<typeof installedSchema>

export type TileAdd = { kind: 'installed_app'; path: string } | { kind: 'website'; label: string; url: string }

export interface TilesApi {
  overview: () => Promise<AppTiles>
  add: (body: TileAdd) => Promise<AppTiles>
  move: (tileId: number, position: number) => Promise<AppTiles>
  restore: (tileId: number) => Promise<AppTiles>
  remove: (tileId: number) => Promise<void>
  reset: () => Promise<AppTiles>
  available: () => Promise<InstalledApp[]>
  /** ``url``: online copy only, a website for this device to open in a new tab. */
  launch?: (tileId: number) => Promise<{ launched: boolean; label: string; url?: string }>
}

function tilesApi(base: string, availablePath: string): TilesApi {
  const parse = (r: { data: unknown }) => tilesSchema.parse(r.data)
  return {
    overview: () => appClient.get(base).then(parse),
    add: (body) => appClient.post(base, body).then(parse),
    move: (tileId, position) => appClient.patch(`${base}/${tileId}`, { position }).then(parse),
    restore: (tileId) => appClient.patch(`${base}/${tileId}`, { is_visible: true }).then(parse),
    remove: (tileId) => appClient.delete(`${base}/${tileId}`).then(() => undefined),
    reset: () => appClient.post(`${base}/reset`).then(parse),
    available: () => appClient.get(availablePath).then((r) => installedSchema.array().parse(r.data)),
  }
}

/** IrisClick Desktop is not running (or the browser blocks it), so programs cannot open. */
export class DesktopNotRunning extends Error {
  constructor() {
    super('Start IrisClick Desktop on this computer to open apps.')
  }
}

const onPcSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('builtin'), key: z.string() }),
  z.object({ kind: z.literal('installed_app'), path: z.string() }),
])
const launchSchema = z.object({
  launched: z.boolean(),
  label: z.string(),
  url: z.url({ protocol: /^https?$/ }).optional(),
  on_pc: onPcSchema.optional(),
})

/** Hosted website: IrisClick Desktop on this PC (127.0.0.1) opens the program. */
function openOnThisPc(onPc: z.infer<typeof onPcSchema>) {
  return apiClient
    .post('/desktop/apps/open', onPc, { timeout: 20000 })
    .then((r) => z.object({ launched: z.boolean(), label: z.string() }).parse(r.data))
    .catch((err: unknown) => {
      if (isAxiosError(err) && !err.response) throw new DesktopNotRunning()
      throw err
    })
}

/** The signed-in assistive user's own tiles. */
export const myTiles: TilesApi = {
  ...tilesApi('/me/apps/tiles', '/me/apps/available'),
  // Hosted website: the Start-menu programs of this PC come from IrisClick Desktop.
  ...(ONLINE_COPY && {
    available: () =>
      apiClient
        .get('/desktop/apps/available', { timeout: 20000 })
        .then((r) => installedSchema.array().parse(r.data))
        .catch((err: unknown) => {
          if (isAxiosError(err) && !err.response) throw new DesktopNotRunning()
          throw err
        }),
  }),
  launch: (tileId) =>
    appClient
      .post(`/me/apps/tiles/${tileId}/launch`)
      .then((r) => launchSchema.parse(r.data))
      .then((result) => (result.on_pc ? openOnThisPc(result.on_pc) : result)),
}

/** One user's tiles, edited by the admin (no launching from the admin pages). */
export const tilesForUser = (userId: number): TilesApi =>
  tilesApi(`/admin/users/${userId}/apps`, `/admin/users/${userId}/apps/available`)
