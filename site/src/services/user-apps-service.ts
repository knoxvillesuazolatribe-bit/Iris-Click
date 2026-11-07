import { z } from 'zod'
import { appClient } from '@/api/app-client'

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

/** The signed-in assistive user's own tiles. */
export const myTiles: TilesApi = {
  ...tilesApi('/me/apps/tiles', '/me/apps/available'),
  launch: (tileId) =>
    appClient
      .post(`/me/apps/tiles/${tileId}/launch`)
      .then((r) => z.object({ launched: z.boolean(), label: z.string(), url: z.url({ protocol: /^https?$/ }).optional() }).parse(r.data)),
}

/** One user's tiles, edited by the admin (no launching from the admin pages). */
export const tilesForUser = (userId: number): TilesApi =>
  tilesApi(`/admin/users/${userId}/apps`, `/admin/users/${userId}/apps/available`)
