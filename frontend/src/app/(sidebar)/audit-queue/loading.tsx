import { Card } from '@/components/scanner-ui'
import { Bone } from '@/components/skeleton'

export default function AuditQueueLoading() {
  return (
    <div className="space-y-6 p-6">
      <div className="space-y-2">
        <Bone.Block className="h-8 w-48" />
        <Bone.Block className="h-4 w-96" />
      </div>

      <Card>
        <div className="space-y-4 p-4">
          <div className="flex gap-2">
            <Bone.Block className="h-8 w-28" />
            <Bone.Block className="h-8 w-28" />
            <Bone.Block className="h-8 w-28" />
          </div>
          <Bone.Block className="h-10 w-full" />
          <Bone.Block className="h-12 w-full" />
          <Bone.Block className="h-12 w-full" />
          <Bone.Block className="h-12 w-full" />
        </div>
      </Card>
    </div>
  )
}
