export function ModelExplanation() {
  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-50 p-5 text-emerald-950">
      <h2 className="text-xl font-black">توضیح مدل</h2>
      <p className="mt-3 leading-8">
        تابع هدف در این پروژه بیشینه‌سازی نسبت شارپ است. محدودیت‌ها شامل مجموع
        وزن‌ها برابر با ۱۰۰٪، ممنوعیت فروش استقراضی و سقف وزن ۳۰٪ برای هر سهم
        است. بنابراین مدل، یک پرتفوی long-only می‌سازد که نسبت بازده مازاد به
        ریسک آن حداکثر شود.
      </p>
    </div>
  )
}
