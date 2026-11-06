// Talky's logo symbol, as published on usetalky.com (public/talky-mark.svg).
export interface TalkyMarkProps {
  /** Width in px; height follows the symbol's aspect ratio. */
  size?: number
  /** Accessible name; omit when text next to the mark already names it. */
  title?: string
  className?: string
}

export function TalkyMark({ size = 22, title, className }: TalkyMarkProps) {
  return <img src="/talky-mark.svg" width={size} alt={title ?? ''} aria-hidden={title ? undefined : true} className={className} />
}
