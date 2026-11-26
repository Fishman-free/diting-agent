import { cn } from '@/lib/utils'

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

// Brand badge: 谛听「墨底鎏金·听波」标记（与桌面图标 assets/diting.ico 同源，
// 见 apps/desktop/public/diting.png）。标记自带圆角方形底与透明边角，两种主题
// 下均使用同一资产；尺寸走 className（默认 size-14）。
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span className={cn('inline-flex size-14 shrink-0 items-center justify-center', className)} {...props}>
      <img alt="" className="size-full object-contain" src={assetPath('diting.png')} />
    </span>
  )
}
