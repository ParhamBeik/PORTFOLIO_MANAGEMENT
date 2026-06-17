const images = [
  {
    src: '/images/optimization_trajectories_all.png',
    caption: 'همه مسیرهای بهینه‌سازی',
  },
  {
    src: '/images/trajectory_Equal_Weight.png',
    caption: 'مسیر شروع با وزن برابر',
  },
  {
    src: '/images/trajectory_Max_Return_Asset.png',
    caption: 'مسیر شروع از سهم با بیشترین بازده',
  },
  {
    src: '/images/trajectory_Minimum_Variance.png',
    caption: 'مسیر شروع از کمترین واریانس',
  },
  {
    src: '/images/trajectory_Sharpe_Proportional.png',
    caption: 'مسیر شروع متناسب با شارپ',
  },
]

export function ImageGallery() {
  return (
    <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
      {images.map((image) => (
        <figure
          key={image.src}
          className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
        >
          <img
            src={image.src}
            alt={image.caption}
            className="aspect-[4/3] w-full bg-slate-50 object-contain p-2"
            loading="lazy"
          />
          <figcaption className="border-t border-slate-100 px-4 py-3 text-sm font-bold text-slate-700">
            {image.caption}
          </figcaption>
        </figure>
      ))}
    </div>
  )
}
