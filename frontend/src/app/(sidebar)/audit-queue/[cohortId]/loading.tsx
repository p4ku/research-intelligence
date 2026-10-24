import { Bone } from '@/components/skeleton'

export default function CohortRedirectLoading() {
  return (
    <div className="flex h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <Bone.Block className="size-8 rounded-full" />
        <Bone.Block className="h-4 w-40" />
      </div>
    </div>
  )
}
