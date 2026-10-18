-- Align demo descriptions and AI reference images with the supplied campus photographs.
update public.found_items set color='Black',description='Black fabric backpack with a white logo, zippered compartments and shoulder straps.',image_path='https://huskyfind-uw.expo.app/demo/backpack.jpg'
where id='10000000-0000-0000-0000-000000000002' and is_demo;
update public.found_items set description='Black over-ear headphones with padded ear cups hanging on a blue chair.',image_path='https://huskyfind-uw.expo.app/demo/headphones.jpg'
where id='10000000-0000-0000-0000-000000000003' and is_demo;
update public.found_items set description='Metal keys and a black key fob on a white table.',image_path='https://huskyfind-uw.expo.app/demo/keys.jpg'
where id='10000000-0000-0000-0000-000000000004' and is_demo;
update public.found_items set title='Black tablet case',category='Accessories',description='Flat black tablet case left on a purple chair.',image_path='https://huskyfind-uw.expo.app/demo/tablet.jpg'
where id='10000000-0000-0000-0000-000000000005' and is_demo;
insert into public.found_items(id,title,description,category,color,image_path,approximate_location,latitude,longitude,source,is_demo)
values('10000000-0000-0000-0000-000000000006','Blue and gold pouch','Small blue fabric pouch with yellow trim, left on a chair.','Bags','Blue','https://huskyfind-uw.expo.app/demo/pouch.jpg','Husky Union Building',47.6553,-122.3051,'community',true);
