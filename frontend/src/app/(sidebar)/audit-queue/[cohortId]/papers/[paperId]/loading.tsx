import { Bone } from '@/components/skeleton'

export default function PaperReviewLoading() {
  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col overflow-hidden bg-zinc-50 dark:bg-zinc-950">
      <div className="flex h-14 items-center justify-between border-b border-zinc-200 bg-white px-4 dark:border-zinc-800 dark:bg-zinc-900">
        <Bone.Block className="h-6 w-48" />
        <Bone.Block className="h-6 w-36" />
        <Bone.Block className="h-6 w-24" />
      </div>

      <div className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-12">
        <div className="h-full border-r border-zinc-200 p-4 lg:col-span-7 dark:border-zinc-800">
          <Bone.Block className="h-full w-full rounded-lg" />
        </div>
        <div className="h-full space-y-4 p-5 lg:col-span-5">
          <Bone.Block className="h-10 w-full" />
          <Bone.Block className="h-28 w-full" />
          <Bone.Block className="h-32 w-full" />
          <Bone.Block className="h-10 w-full" />
        </div>
      </div>
    </div>
  )
}
