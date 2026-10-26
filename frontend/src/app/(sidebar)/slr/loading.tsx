export default function SlrLoading() {
  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="h-16 w-full animate-pulse rounded-2xl bg-zinc-100 dark:bg-zinc-800" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-28 animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-800" />
        ))}
      </div>
      <div className="h-96 w-full animate-pulse rounded-2xl bg-zinc-100 dark:bg-zinc-800" />
    </div>
  )
}
