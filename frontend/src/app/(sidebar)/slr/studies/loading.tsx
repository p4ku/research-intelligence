export default function SLRStudiesLoading() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* Top Bar Skeleton */}
      <div className="h-20 w-full animate-pulse rounded-2xl bg-zinc-100 dark:bg-zinc-800" />

      {/* KPI Cards Skeleton */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-800" />
        ))}
      </div>

      {/* Filter Bar Skeleton */}
      <div className="h-14 w-full animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-800" />

      {/* Table Skeleton */}
      <div className="h-96 w-full animate-pulse rounded-2xl bg-zinc-100 dark:bg-zinc-800" />
    </div>
  )
}
