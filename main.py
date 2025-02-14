import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import psutil


class AvitoParse:
    def __init__(self, product_name_search: str, version_brow=None):
        self.driver = None
        self.product_name_search = product_name_search.replace(" ", "")
        self.url = "https://www.avito.ru/all?cd=1&q=" + self.product_name_search + "&s=104"
        self.version_brow = version_brow
        self.product_data = dict()
        self.final_id_product = 0

    def set_up(self):
        options = uc.ChromeOptions()
        options.add_argument('--headless')  # Режим без графического интерфейса
        options.add_argument('--disable-gpu')  # Отключение GPU для ускорения
        options.add_argument('--no-sandbox')  # Для серверов
        options.add_argument('--disable-dev-shm-usage')  # Оптимизация использования памяти
        options.add_argument('--disable-blink-features=AutomationControlled')  # Скрытие факта автоматизации
        options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')  # Пользовательский агент

        # Настройки для уменьшения загрузки ресурсов
        options.experimental_options["prefs"] = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.stylesheets": 2,
            "profile.managed_default_content_settings.fonts": 2,
            "profile.managed_default_content_settings.cookies": 2,
        }

        self.driver = uc.Chrome(version_main=self.version_brow, options=options)

    def cleanup_driver(self):
        """Закрытие драйвера и всех связанных процессов."""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
        # Убиваем все дочерние процессы (например, браузерные процессы)
        for proc in psutil.process_iter(['pid', 'name']):
            if 'chromedriver' in proc.info['name'] or 'chrome' in proc.info['name']:
                try:
                    psutil.Process(proc.info['pid']).terminate()
                except psutil.NoSuchProcess:
                    pass

    def get_url(self):
        self.driver.get(self.url)

    def get_pictures(self, title):
        image_elements = title.find_elements(By.CSS_SELECTOR, "img[itemprop='image']")

        images_high_res = []
        for img in image_elements:
            srcset = img.get_attribute("srcset")
            if srcset:
                largest_image = srcset.split(",")[-1].split(" ")[0]
                images_high_res.append(largest_image)
            else:
                images_high_res.append(img.get_attribute("src"))
        return tuple(images_high_res)

    def parse_page(self):
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-marker='item']"))
            )
            title = self.driver.find_element(By.CSS_SELECTOR, "[data-marker='item']")
            name_product = title.find_element(By.CSS_SELECTOR, "[itemprop='name']").text
            cost_product = title.find_element(By.CSS_SELECTOR, "[itemprop='price']").get_attribute("content")
            id_product = title.get_attribute("data-item-id")
            about_product = title.find_element(By.CSS_SELECTOR, "[class*='iva-item-descriptionStep").text[:200]
            url_product = title.find_element(By.CSS_SELECTOR, "[itemprop='url']").get_attribute("href")
            pictures_product = self.get_pictures(title)
            self.product_data.clear()
            self.product_data[id_product] = [
                name_product,
                cost_product,
                about_product,
                url_product,
                pictures_product
            ]
        finally:
            self.cleanup_driver()

    def parse(self):
        self.set_up()
        self.get_url()
        self.parse_page()

    def updates_product(self):
        if list(self.product_data.keys())[0] == self.final_id_product:
            self.product_data.clear()
            return None
        else:
            self.final_id_product = list(self.product_data.keys())[0]
            self.product_data = {self.final_id_product: self.product_data[self.final_id_product]}
            return self.product_data


