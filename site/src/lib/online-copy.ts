/**
 * True only in the online copy built on Vercel (vercel.json sets VITE_IRISCLICK_ONLINE=1).
 * The PC build is unchanged: every check on this flag leaves it exactly as before.
 */
export const ONLINE_COPY = import.meta.env.VITE_IRISCLICK_ONLINE === '1'
